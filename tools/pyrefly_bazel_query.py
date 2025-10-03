#!/usr/bin/env python3
"""
Bazel-backed source DB query for Pyrefly-style integration.

Usage:
  python3 tools/pyrefly_bazel_query.py --file path1.py --file path2.py ...

It prints a JSON object like:

{
  "db": {
    "<dist>": {
      "srcs": { "<module>": ["path/to/file.py"], ... },
      "deps": ["<dist_dep1>", ...],
      "python_version": "3.11",
      "python_platform": "linux|macosx|windows"
    },
    ...
  },
  "root": "/abs/path/to/workspace"
}

Heuristics:
- <dist> is inferred from the first path segment of each target's Python sources.
- For py_library, module keys are full dotted import paths (e.g., "click.core").
- For py_binary, module keys are shortened to the basename (e.g., "main").
- Direct dependencies are inferred via Bazel "labels('deps', <label>)" and mapped to their dist names.
"""
import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from typing import Dict, List, Set

def run(cmd: List[str], cwd: str = None) -> str:
    res = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}")
    return res.stdout.strip()

def bazel_info_workspace() -> str:
    return run(["bazel", "info", "workspace"])

def bazel_query(query: str, output: str = None) -> List[str]:
    args = ["bazel", "query", query, "--keep_going", "--noshow_progress"]
    if output:
        args.extend(["--output", output])
    out = run(args)
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return lines

def label_kind(label: str) -> str:
    # Returns e.g. "py_library rule //path:target"
    lines = bazel_query(label, output="label_kind")
    if not lines:
        return ""
    return lines[0].split()[0]  # "py_library" or "py_binary" etc.

def file_label_to_path(file_label: str) -> str:
    # Local file label looks like //pkg:filename.py -> pkg/filename.py
    if not file_label.startswith("//"):
        return file_label  # external or unexpected; return as-is
    pkg_and_file = file_label[2:]
    if ":" in pkg_and_file:
        pkg, fname = pkg_and_file.split(":", 1)
        return f"{pkg}/{fname}"
    return pkg_and_file  # fallback

def infer_dist_name(src_paths: List[str]) -> str:
    # Choose the most common top-level directory among srcs
    counts = defaultdict(int)
    for p in src_paths:
        parts = p.split("/")
        if parts:
            counts[parts[0]] += 1
    if not counts:
        return "unknown"
    max_count = max(counts.values())
    candidates = [k for k, v in counts.items() if v == max_count]
    return sorted(candidates)[0]

def module_name_from_path(path: str) -> str:
    # Convert path/to/file.py -> path.to.file ; strip .py ; special-case __init__.py
    if not path.endswith(".py"):
        return path.replace("/", ".")
    mod = path[:-3].replace("/", ".")
    if mod.endswith(".__init__"):
        mod = mod[: -len(".__init__")]
    return mod

def system_python_platform() -> str:
    p = sys.platform
    if p.startswith("linux"):
        return "linux"
    if p == "darwin":
        return "macosx"
    if p.startswith("win"):
        return "windows"
    return p

def collect_py_target_info(target_label: str, cache: Dict[str, dict]) -> dict:
    if target_label in cache:
        return cache[target_label]

    kind = label_kind(target_label)
    file_labels = bazel_query(f"labels('srcs', {target_label})")
    src_paths = [file_label_to_path(fl) for fl in file_labels]

    dep_labels = bazel_query(f"labels('deps', {target_label})")
    py_dep_labels = []
    for dl in dep_labels:
        k = label_kind(dl)
        if k.startswith("py_"):
            py_dep_labels.append(dl)

    dist = infer_dist_name(src_paths) if src_paths else "unknown"

    info = {
        "kind": kind,
        "src_paths": src_paths,
        "dist": dist,
        "deps_labels": py_dep_labels,
    }
    cache[target_label] = info
    return info

# Replace the existing build_db_for_files(...) with this implementation.

def build_db_for_files(file_paths: List[str]) -> dict:
    workspace = bazel_info_workspace()

    # 1) gather all python targets in workspace
    all_py_targets = bazel_query("kind('py_.* rule', //...)")

    # 2) build file -> owning-targets map
    file_to_targets: Dict[str, List[str]] = {}
    for tgt in all_py_targets:
        # get srcs labels for this target
        file_labels = bazel_query(f"labels('srcs', {tgt})")
        for fl in file_labels:
            # convert label to workspace-relative path (e.g. //pkg:foo.py -> pkg/foo.py)
            path = file_label_to_path(fl)
            file_to_targets.setdefault(path, []).append(tgt)

    # 3) determine target set for the requested files (normalize paths relative to workspace)
    requested_targets: Set[str] = set()
    for fp in file_paths:
        abs_fp = os.path.abspath(fp)
        if abs_fp.startswith(workspace):
            rel = os.path.relpath(abs_fp, workspace)
        else:
            rel = fp
        # try exact match
        owners = file_to_targets.get(rel, [])
        # also try matching by basename or subpath variants if needed
        if not owners:
            # attempt to match label forms: sometimes label->path mapping produces pkg/foo.py vs pkg/sub:foo.py variants
            # try to find any key that endswith the rel (best-effort)
            for key, tgts in file_to_targets.items():
                if key.endswith(rel):
                    owners.extend(tgts)
        for o in owners:
            requested_targets.add(o)

    # 4) now traverse the targets and their direct deps (depth-first) and collect info
    info_cache: Dict[str, dict] = {}
    seen: Set[str] = set()
    order: List[str] = []

    def dfs(label: str):
        if label in seen:
            return
        seen.add(label)
        info = collect_py_target_info(label, info_cache)
        for d in info["deps_labels"]:
            dfs(d)
        order.append(label)

    for t in sorted(requested_targets):
        dfs(t)

    # 5) build result_db in the same way as before
    result_db: Dict[str, dict] = {}
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    py_plat = system_python_platform()

    def add_entry(dist: str, srcs_map: Dict[str, List[str]], deps_dists: List[str]):
        if dist not in result_db:
            result_db[dist] = {
                "srcs": {},
                "deps": [],
                "python_version": py_ver,
                "python_platform": py_plat,
            }
        for mod, paths in srcs_map.items():
            result_db[dist]["srcs"].setdefault(mod, [])
            for p in paths:
                if p not in result_db[dist]["srcs"][mod]:
                    result_db[dist]["srcs"][mod].append(p)
        for d in deps_dists:
            if d not in result_db[dist]["deps"]:
                result_db[dist]["deps"].append(d)

    for label in order:
        info = info_cache[label]
        dist = info["dist"]
        module_map: Dict[str, List[str]] = {}
        if info["kind"].startswith("py_binary"):
            for p in info["src_paths"]:
                full = module_name_from_path(p)
                short = full.split(".")[-1]
                module_map.setdefault(short, []).append(p)
        else:
            for p in info["src_paths"]:
                mod = module_name_from_path(p)
                module_map.setdefault(mod, []).append(p)

        deps_dists: List[str] = []
        for dl in info["deps_labels"]:
            d_info = info_cache.get(dl) or collect_py_target_info(dl, info_cache)
            if d_info["dist"] not in deps_dists:
                deps_dists.append(d_info["dist"])

        add_entry(dist, module_map, deps_dists)

    return {
        "db": result_db,
        "root": workspace,
    }


def main():
    ap = argparse.ArgumentParser(description="Query Bazel for Python source DB (Pyrefly-style).")
    ap.add_argument("--file", dest="files", action="append", default=[], help="A Python source file (repeatable).")
    args = ap.parse_args()

    if not args.files:
        print(json.dumps({"error": "No --file arguments provided"}), flush=True)
        sys.exit(2)

    out = build_db_for_files(args.files)
    print(json.dumps(out, indent=2), flush=True)

if __name__ == "__main__":
    main()
