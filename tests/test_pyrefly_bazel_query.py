"""Tests for tools.pyrefly_bazel_query using a stubbed Bazel executable."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Iterable, List

import pytest

from tools.pyrefly_bazel_query import system_python_platform


REPO_ROOT = Path(__file__).resolve().parents[1]
STUB_DIR = REPO_ROOT / "tests" / "fixtures"
BASE_FIXTURE = STUB_DIR / "bazel_command_map.json"

if not (STUB_DIR / "bazel").exists():  # pragma: no cover - guard for missing stub
    pytest.skip("Bazel stub not found; ensure Bazel is available in PATH.", allow_module_level=True)


def _prepare_env(
    fixture_path: Path,
    *,
    extra_env: Dict[str, str] | None = None,
    log_path: Path | None = None,
) -> Dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{STUB_DIR}:{env.get('PATH', '')}"
    env["BAZEL_STUB_WORKSPACE"] = str(REPO_ROOT)
    env["BAZEL_STUB_FIXTURES"] = str(fixture_path)
    if log_path is not None:
        env["BAZEL_STUB_LOG"] = str(log_path)
    if extra_env:
        env.update(extra_env)
    return env


def _run_tool(
    files: Iterable[str],
    *,
    fixture_path: Path = BASE_FIXTURE,
    extra_env: Dict[str, str] | None = None,
    log_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    file_args = list(files)
    with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
        for file_arg in file_args:
            tmp.write("--file\n")
            tmp.write(f"{file_arg}\n")
        tmp_path = Path(tmp.name)
    cmd: List[str] = [
        sys.executable,
        str(REPO_ROOT / "tools" / "pyrefly_bazel_query.py"),
        f"@{tmp_path}",
    ]
    env = _prepare_env(fixture_path, extra_env=extra_env, log_path=log_path)
    try:
        return subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:  # pragma: no cover - ignore clean-up race
            pass


def _load_snapshot(snapshot_path: Path) -> Dict[str, object]:
    raw = snapshot_path.read_text(encoding="utf-8")
    replacements = {
        "__PY_VERSION__": f"{sys.version_info.major}.{sys.version_info.minor}",
        "__PY_PLATFORM__": system_python_platform(),
        "__WORKSPACE_ROOT__": str(REPO_ROOT),
    }
    for placeholder, value in replacements.items():
        raw = raw.replace(placeholder, value)
    return json.loads(raw)


def _assert_distribution_entry(entry: Dict[str, object]) -> None:
    required_keys = {"srcs", "deps", "python_version", "python_platform", "buildfile_path"}
    assert required_keys == set(entry.keys())
    assert entry["python_version"] == f"{sys.version_info.major}.{sys.version_info.minor}"
    assert entry["python_platform"] == system_python_platform()
    assert isinstance(entry["buildfile_path"], str)
    if entry["buildfile_path"]:
        assert entry["buildfile_path"].startswith("//")
    assert isinstance(entry["deps"], list)
    for dep in entry["deps"]:
        assert isinstance(dep, str)
    srcs = entry["srcs"]
    assert isinstance(srcs, dict)
    for module, files in srcs.items():
        assert isinstance(module, str)
        assert isinstance(files, list)
        for file_path in files:
            assert isinstance(file_path, str)


def test_single_file_query_matches_expected_snapshot() -> None:
    result = _run_tool(["my_project/main.py"])
    assert result.returncode == 0, result.stderr
    actual = json.loads(result.stdout)
    expected = _load_snapshot(REPO_ROOT / "tests/expected_outputs/basic_single_file.json")
    assert actual == expected


def test_json_schema_validation() -> None:
    result = _run_tool(["my_project/main.py"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert set(payload.keys()) == {"db", "root"}
    assert payload["root"] == str(REPO_ROOT)
    db = payload["db"]
    assert isinstance(db, dict)
    assert db, "expected db to contain distributions"
    for dist_name, entry in db.items():
        assert isinstance(dist_name, str)
        _assert_distribution_entry(entry)


def test_multi_file_query_includes_full_project_snapshot() -> None:
    files = [
        "my_project/main.py",
        "libs/common/formatters.py",
        "plugins/analyzer.py",
        "scripts/run_report.py",
        "services/reporting/report_cli.py",
    ]
    result = _run_tool(files)
    assert result.returncode == 0, result.stderr
    actual = json.loads(result.stdout)
    expected = _load_snapshot(REPO_ROOT / "tests/expected_outputs/full_project.json")
    assert actual == expected


def test_dependency_resolution_captures_transitive_and_self_dependencies() -> None:
    result = _run_tool(["services/reporting/report_cli.py"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    db = payload["db"]
    assert set(db["//services/reporting:report_cli"]["deps"]) == {
        "//click:click_lib",
        "//services/reporting:reporting_lib",
    }
    assert "//plugins:analyzer" not in db, "plugins should not appear when querying only reporting files"
    assert set(db["//services/reporting:reporting_lib"]["deps"]) == {
        "//libs/common:common_utils"
    }
    assert set(db["//click:click_lib"]["deps"]) == {"//colorama:colorama_lib"}


def test_module_path_resolution_for_libraries_binaries_and_packages() -> None:
    result = _run_tool([
        "scripts/run_report.py",
        "click/core.py",
        "plugins/analyzer.py",
    ])
    assert result.returncode == 0, result.stderr
    db = json.loads(result.stdout)["db"]

    # py_binary short module name
    assert "run_report" in db["//scripts:run_report"]["srcs"]
    assert db["//scripts:run_report"]["srcs"]["run_report"] == ["scripts/run_report.py"]

    # py_library full dotted path
    assert "click.core" in db["//click:click_lib"]["srcs"]
    assert "click" in db["//click:click_lib"]["srcs"]

    # package __init__ flattened correctly
    assert "plugins" in db["//plugins:analyzer"]["srcs"]
    assert "plugins.analyzer" in db["//plugins:analyzer"]["srcs"]


def test_invalid_file_path_returns_empty_database() -> None:
    result = _run_tool(["nonexistent/file.py"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["db"] == {}
    assert payload["root"] == str(REPO_ROOT)


def test_no_arguments_returns_error_json() -> None:
    cmd = [sys.executable, str(REPO_ROOT / "tools" / "pyrefly_bazel_query.py")]
    env = _prepare_env(BASE_FIXTURE)
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"error": "Usage: script.py @/path/to/list.txt"}


def test_command_handles_bazel_warnings(tmp_path: Path) -> None:
    fixture = json.loads(BASE_FIXTURE.read_text(encoding="utf-8"))
    key = json.dumps([
        "query",
        "labels('deps', //click:click_lib)",
        "--keep_going",
        "--noshow_progress",
    ])
    entry = fixture["commands"][key]
    entry["stderr"] = "WARNING: some Bazel warning about embedded tools\n"
    entry["returncode"] = 3
    warning_fixture = tmp_path / "bazel_warning.json"
    warning_fixture.write_text(json.dumps(fixture, indent=2), encoding="utf-8")

    result = _run_tool(["click/core.py"], fixture_path=warning_fixture)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert "//click:click_lib" in payload["db"]


def test_python_version_and_platform_detection_consistent_with_runtime() -> None:
    result = _run_tool(["my_project/main.py"])
    payload = json.loads(result.stdout)
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    platform = system_python_platform()
    for entry in payload["db"].values():
        assert entry["python_version"] == version
        assert entry["python_platform"] == platform


def test_regression_snapshot_matches_expected_full_project() -> None:
    result = _run_tool([
        "my_project/main.py",
        "plugins/analyzer.py",
        "scripts/run_report.py",
        "services/reporting/report_cli.py",
    ])
    assert result.returncode == 0, result.stderr
    actual = json.loads(result.stdout)
    expected = _load_snapshot(REPO_ROOT / "tests/expected_outputs/full_project.json")
    assert actual == expected


def test_large_project_performance(tmp_path: Path) -> None:
    size = 25
    commands: Dict[str, Dict[str, object]] = {}

    def k(args: List[str]) -> str:
        return json.dumps(args)

    all_targets: List[str] = [f"//pkg{i}:lib{i}" for i in range(size)]
    commands[k([
        "query",
        "kind('py_.* rule', //...)",
        "--keep_going",
        "--noshow_progress",
    ])] = {"stdout": "\n".join(all_targets) + "\n", "stderr": "", "returncode": 0}

    for idx, label in enumerate(all_targets):
        src = f"//pkg{idx}:module{idx}.py"
        commands[k([
            "query",
            f"labels('srcs', {label})",
            "--keep_going",
            "--noshow_progress",
        ])] = {"stdout": f"{src}\n", "stderr": "", "returncode": 0}
        dep_label = all_targets[idx + 1] if idx + 1 < size else ""
        dep_stdout = f"{dep_label}\n" if dep_label else ""
        commands[k([
            "query",
            f"labels('deps', {label})",
            "--keep_going",
            "--noshow_progress",
        ])] = {"stdout": dep_stdout, "stderr": "", "returncode": 0}
        commands[k([
            "query",
            label,
            "--keep_going",
            "--noshow_progress",
            "--output",
            "label_kind",
        ])] = {"stdout": f"py_library rule {label}\n", "stderr": "", "returncode": 0}

    large_fixture = tmp_path / "bazel_large_project.json"
    large_fixture.write_text(json.dumps({"commands": commands}, indent=2), encoding="utf-8")

    start = time.perf_counter()
    result = _run_tool(["pkg0/module0.py"], fixture_path=large_fixture)
    duration = time.perf_counter() - start

    assert result.returncode == 0, result.stderr
    assert duration < 6, f"Query should finish quickly, took {duration:.2f}s"
    payload = json.loads(result.stdout)
    assert len(payload["db"]) == size


def test_query_efficiency_minimises_redundant_label_kind_calls(tmp_path: Path) -> None:
    log_path = tmp_path / "bazel_log.txt"
    result = _run_tool(["my_project/main.py"], log_path=log_path)
    assert result.returncode == 0, result.stderr

    label_kind_calls = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        args = json.loads(line)
        if args[:2] == ["query", "kind('py_.* rule', //...)"]:
            continue
        if args[-2:] == ["--output", "label_kind"]:
            label_kind_calls.append(args[1])

    assert label_kind_calls, "expected at least one label_kind query"
    assert len(label_kind_calls) == len(set(label_kind_calls)), "label_kind queries should be cached per label"
