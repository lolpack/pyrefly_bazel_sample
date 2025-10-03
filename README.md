# Pyrefly + Bazel (Python) — Sample Project

⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️ WARNING - EXPERIMENTAL I HAVE NO IDEA IF THIS WORKS YET

This is a **minimal, working** sample that shows how to integrate Bazel with Pyrefly by replacing the existing `buck2 bxl prelude//python/sourcedb/pyrefly.bxl:main` call with a **script that shells out to Bazel** and emits the **Pyrefly source DB JSON**.

It contains:
- A tiny Python workspace with three packages: `colorama`, `click` (both stubbed), and `my_project` (a runnable binary).
- A script: `tools/pyrefly_bazel_query.py` that:
  - accepts repeated `--file <path>` args
  - runs `bazel query` to discover the owning targets + direct deps
  - builds a JSON **file-path DB** in the shape Pyrefly expects
- Step‑by‑step instructions for installing Bazel and running everything (no prior Bazel knowledge needed).

---

## 0) Prereqs

- **Python**: install Python 3.10+ (3.11 recommended).
- **Bazel**: install [Bazelisk](https://github.com/bazelbuild/bazelisk) which provides the `bazel` command.

### macOS (Homebrew)

```bash
brew install bazelisk
```

Or follow the instructions here [https://bazel.build/install/os-x](https://bazel.build/install/os-x)


### Linux

```bash
# On Debian/Ubuntu (via npm):
sudo apt-get install -y npm
sudo npm -g install @bazel/bazelisk

# Or download a Bazelisk release binary:
# https://github.com/bazelbuild/bazelisk/releases
```

### Windows

Install Bazelisk from the releases page and ensure `bazel.exe` is on your PATH.

> If you already have Bazel installed, that’s fine—Bazelisk will just proxy to the appropriate Bazel version.

---

## 1) Clone the repo

```bash
cd pyrefly_bazel_sample
```

Take a quick look at the layout:

```
.
├── WORKSPACE.bazel
├── colorama
│   ├── BUILD.bazel
│   ├── __init__.py
│   └── ansi.py
├── click
│   ├── BUILD.bazel
│   ├── __init__.py
│   └── core.py
├── my_project
│   ├── BUILD.bazel
│   └── main.py
└── tools
    └── pyrefly_bazel_query.py
```

---

## 2) First build & run (sanity check)

This repo uses [`rules_python`](https://github.com/bazelbuild/rules_python) and registers a hermetic Python 3.11 toolchain automatically.

```bash
# Print Bazel's idea of the workspace root (just to verify pathing)
bazel info workspace

# Build everything:
bazel build 

# Run the example binary:
bazel run //my_project:main
```

You should see:

```
[blue]Hello from my_project![/blue]
```

---

## 3) Produce the Pyrefly-style Source DB via Bazel

The script **accepts the same arguments** your Pyrefly integration passes today: repeated `--file <path>`.  
Paths should be **relative to the repo root** (what `bazel info workspace` prints).

Examples:

```bash
# Query for just the binary's main file
python3 tools/pyrefly_bazel_query.py   --file my_project/main.py | jq .

# Query for everything (binary + libraries)
python3 tools/pyrefly_bazel_query.py   --file my_project/main.py   --file click/core.py   --file colorama/ansi.py | jq .
```

Expected JSON **shape** (values will show your absolute workspace path and Python version/platform):

```json
{
  "db": {
    "colorama": {
      "srcs": {
        "colorama": ["colorama/__init__.py"],
        "colorama.ansi": ["colorama/ansi.py"]
      },
      "deps": [],
      "python_version": "3.11",
      "python_platform": "linux|macosx|windows"
    },
    "click": {
      "srcs": {
        "click": ["click/__init__.py"],
        "click.core": ["click/core.py"]
      },
      "deps": ["colorama"],
      "python_version": "3.11",
      "python_platform": "linux|macosx|windows"
    },
    "my_project": {
      "srcs": {
        "main": ["my_project/main.py"]
      },
      "deps": ["click"],
      "python_version": "3.11",
      "python_platform": "linux|macosx|windows"
    }
  },
  "root": "/abs/path/to/your/workspace"
}
```

> **Notes on heuristics**
>
> - The top‑level keys (`colorama`, `click`, `my_project`) are inferred from each target’s source roots.
> - For `py_library` targets we use **full import paths** as module keys (`click.core`, `colorama.ansi`).
> - For `py_binary` targets we shorten to the **basename** (e.g., `main`) to better match Pyrefly’s example.
> - Direct deps are discovered via `labels('deps', <label>)` and mapped to their inferred dist names.

---

## 4) Wire this into Pyrefly

In Pyrefly’s build integration, where you currently do:

```rust
let mut cmd = Command::new("buck2");
cmd.arg("bxl");
cmd.arg("--reuse-current-config");
cmd.arg("prelude//python/sourcedb/pyrefly.bxl:main");
cmd.arg("--");
cmd.args(files.flat_map(|f| ["--file", f]));
cmd.current_dir(cwd);
```

Replace that with (conceptually):

```rust
let mut cmd = Command::new("python3");
cmd.arg("tools/pyrefly_bazel_query.py");
cmd.arg("--");
cmd.args(files.flat_map(|f| ["--file", f]));
cmd.current_dir(cwd);
```

…or call the script directly if you make it executable and on your PATH.

The script’s **stdout** is the JSON blob (as bytes), ready for Pyrefly to consume.
