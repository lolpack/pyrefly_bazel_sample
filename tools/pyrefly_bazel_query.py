#!/usr/bin/env python3
"""
Bazel-backed source DB query for Pyrefly-style integration.

Usage:
  python3 tools/pyrefly_bazel_query.py @/path/to/file_list.txt

Output JSON shape:

{
  "db": {
    "//services/reporting:report_cli": {
      "srcs": { "<module>": ["path/to/file.py", ...], ... },
      "deps": ["//colorama:colorama_lib", "//services/reporting:reporting_lib", ...],
      "python_version": "3.12",
      "python_platform": "macosx",
      "buildfile_path": "//services/reporting/BUILD.bazel"
    },
    ...
  },
  "root": "/abs/path/to/workspace"
}

Notes:
- Keys are ALWAYS unique Bazel labels for the owning targets (no dist heuristics).
- Deps are emitted as Bazel labels of *python* deps only (py_*).
- buildfile_path is workspace-relative and prefixed with // (e.g. //pkg/sub/BUILD.bazel).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, MutableMapping, Optional, Set, TypedDict

# -------------------------
# Logging
# Uncomment to debug the bazel query
# -------------------------
def log(message, file="app.log"):
    # pass
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(file, "a") as f:
        f.write(f"{ts} - {message}\n")


# -------------------------
# Types
# -------------------------
class TargetInfo(TypedDict):
    kind: str
    src_paths: List[str]
    deps_labels: List[str]  # only py_* deps


class DistributionEntry(TypedDict):
    srcs: Dict[str, List[str]]
    deps: List[str]  # Bazel labels
    python_version: str
    python_platform: str
    buildfile_path: str


class BuildDbResult(TypedDict):
    db: Dict[str, DistributionEntry]
    root: str


# -------------------------
# Bazel helpers
# -------------------------
def run(cmd: List[str], cwd: Optional[str] = None) -> str:
    res = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    # Allow warnings (non-zero) if stdout still produced something useful
    if res.returncode != 0 and not res.stdout.strip():
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}")
    if res.stderr.strip():
        log(f"bazel stderr for {' '.join(cmd)}:\n{res.stderr}", "bazel.log")
    return res.stdout.strip()


def bazel_info_workspace() -> str:
    return run(["bazel", "info", "workspace"])


def bazel_query(query: str, output: Optional[str] = None) -> List[str]:
    args = ["bazel", "query", query, "--keep_going", "--noshow_progress"]
    if output:
        args.extend(["--output", output])
    out = run(args)
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def label_kind(label: str) -> str:
    # "py_library rule //path:target" -> "py_library"
    lines = bazel_query(label, output="label_kind")
    log(lines, "bazel.log")
    if not lines:
        return ""
    return lines[0].split()[0]


def file_label_to_path(file_label: str) -> str:
    # //pkg:filename.py -> pkg/filename.py
    if not file_label.startswith("//"):
        return file_label
    pkg_and_file = file_label[2:]
    if ":" in pkg_and_file:
        pkg, fname = pkg_and_file.split(":", 1)
        return f"{pkg}/{fname}"
    return pkg_and_file


def module_name_from_path(path: str) -> str:
    # path/to/__init__.py -> path.to ; path/to/file.py -> path.to.file
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


label_kind_cache: Dict[str, str] = {}


def cached_label_kind(label: str) -> str:
    k = label_kind_cache.get(label)
    if k is not None:
        return k
    k = label_kind(label)
    label_kind_cache[label] = k
    return k


def buildfile_for_label(label: str, workspace: str) -> str:
    """
    //pkg/sub:target -> /abs/workspace/pkg/sub/BUILD.bazel | BUILD (absolute path)
    """
    if not label.startswith("//"):
        return ""
    pkg = label[2:].split(":", 1)[0]
    cands = [os.path.join(workspace, pkg, "BUILD.bazel"), os.path.join(workspace, pkg, "BUILD")]
    for cand in cands:
        if os.path.exists(cand):
            return cand
    return ""


def relativize_buildfile_path(abs_buildfile: str, workspace: str) -> str:
    """
    Convert an absolute buildfile path under the workspace to //-prefixed workspace-relative form.
    /abs/workspace/pkg/sub/BUILD.bazel -> //pkg/sub/BUILD.bazel
    If not under workspace, return as-is.
    """
    if not abs_buildfile:
        return ""
    # Normalize to avoid subtle path issues
    workspace = os.path.normpath(workspace)
    abs_buildfile = os.path.normpath(abs_buildfile)
    if abs_buildfile.startswith(workspace + os.sep):
        rel = os.path.relpath(abs_buildfile, workspace)
        # Always use forward slashes in Bazel-style paths
        rel = rel.replace(os.sep, "/")
        return f"//{rel}"
    return abs_buildfile


# -------------------------
# Collect per-target info
# -------------------------
def collect_py_target_info(target_label: str, cache: MutableMapping[str, TargetInfo]) -> TargetInfo:
    log([target_label], "bazel.log")
    if target_label in cache:
        return cache[target_label]

    kind = cached_label_kind(target_label)
    file_labels = bazel_query(f"labels('srcs', {target_label})")
    src_paths = [file_label_to_path(fl) for fl in file_labels]

    dep_labels_all = bazel_query(f"labels('deps', {target_label})")
    py_dep_labels: List[str] = []
    for dl in dep_labels_all:
        k = cached_label_kind(dl)
        if k.startswith("py_"):
            py_dep_labels.append(dl)

    info: TargetInfo = {
        "kind": kind,
        "src_paths": src_paths,
        "deps_labels": py_dep_labels,
    }
    cache[target_label] = info
    return info


# -------------------------
# Build database (labels as keys)
# -------------------------
def build_db_for_files(file_paths: List[str]) -> BuildDbResult:
    workspace = bazel_info_workspace()

    # 1) enumerate all python targets
    all_py_targets = bazel_query("kind('py_.* rule', //...)")

    # 2) map "file path -> owning targets"
    file_to_targets: Dict[str, List[str]] = {}
    for tgt in all_py_targets:
        file_labels = bazel_query(f"labels('srcs', {tgt})")
        for fl in file_labels:
            path = file_label_to_path(fl)
            file_to_targets.setdefault(path, []).append(tgt)

    # 3) determine owning targets for requested files
    requested_targets: Set[str] = set()
    for fp in file_paths:
        abs_fp = os.path.abspath(fp)
        rel = os.path.relpath(abs_fp, workspace) if abs_fp.startswith(workspace) else fp
        owners = file_to_targets.get(rel, [])
        if not owners:
            # fall back: suffix match
            for key, tgts in file_to_targets.items():
                if key.endswith(rel):
                    owners.extend(tgts)
        for o in owners:
            requested_targets.add(o)

    # 4) DFS through py deps
    info_cache: MutableMapping[str, TargetInfo] = {}
    seen: Set[str] = set()
    topo: List[str] = []

    def dfs(label: str) -> None:
        if label in seen:
            return
        seen.add(label)
        info = collect_py_target_info(label, info_cache)
        for d in info["deps_labels"]:
            dfs(d)
        topo.append(label)

    for t in sorted(requested_targets):
        dfs(t)

    # 5) Build result database with LABEL KEYS and LABEL DEPS
    result_db: Dict[str, DistributionEntry] = {}
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    py_plat = system_python_platform()

    def add_entry(label_key: str, srcs_map: Dict[str, List[str]], dep_labels: List[str], abs_buildfile_path: str) -> None:
        buildfile_path = relativize_buildfile_path(abs_buildfile_path, workspace)
        if label_key not in result_db:
            result_db[label_key] = {
                "srcs": {},
                "deps": [],
                "python_version": py_ver,
                "python_platform": py_plat,
                "buildfile_path": buildfile_path,
            }
        ent = result_db[label_key]
        # If the entry already existed (multiple passes), ensure buildfile_path is set to the //-form
        if not ent.get("buildfile_path"):
            ent["buildfile_path"] = buildfile_path

        for mod, paths in srcs_map.items():
            ent["srcs"].setdefault(mod, [])
            for p in paths:
                if p not in ent["srcs"][mod]:
                    ent["srcs"][mod].append(p)
        for d in dep_labels:
            if d not in ent["deps"]:
                ent["deps"].append(d)

    for label in topo:
        info = info_cache[label]

        # module map: py_binary shortens to basename, py_library keeps full dotted path
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

        abs_buildfile_path = buildfile_for_label(label, workspace)
        add_entry(label, module_map, info["deps_labels"], abs_buildfile_path)

    return {"db": result_db, "root": workspace}


# -------------------------
# File-list parsing + CLI
# -------------------------
def parse_file_list(file_path: str) -> List[str]:
    """Reads the file and extracts all file paths after '--file' lines."""
    files: List[str] = []
    try:
        with open(file_path, "r") as f:
            lines = [line.strip() for line in f if line.strip()]
        for i, line in enumerate(lines):
            if line == "--file" and i + 1 < len(lines):
                files.append(lines[i + 1])
    except Exception as e:
        print(json.dumps({"error": f"Failed to read file list: {e}"}), flush=True)
        sys.exit(2)
    return files


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: script.py @/path/to/list.txt"}), flush=True)
        sys.exit(2)

    arg = sys.argv[1]
    if not arg.startswith("@"):
        print(json.dumps({"error": "Expected an argument starting with @"}), flush=True)
        sys.exit(2)

    file_list_path = arg[1:]
    files = parse_file_list(file_list_path)

    if not files:
        print(json.dumps({"error": "No files found in list"}), flush=True)
        sys.exit(2)

    out = build_db_for_files(files)
    log(json.dumps(out, indent=2), "dumps.log")
    print(json.dumps(out, indent=2), flush=True)
