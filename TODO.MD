# TODO: Tests for pyrefly_bazel_query.py

## Overview
Add comprehensive tests for the `tools/pyrefly_bazel_query.py` script to ensure it correctly analyzes Bazel Python targets and produces the expected JSON output format.

## Test Structure
Create test files under `tests/` directory:
- `tests/test_pyrefly_bazel_query.py` - Main test file
- `tests/fixtures/` - Test fixture files with known project structures
- `tests/expected_outputs/` - Expected JSON outputs for validation

## Test Cases to Implement

### 1. Basic Functionality Tests
- **Test Single File Query**: 
  - Command: `python3 tools/pyrefly_bazel_query.py --file my_project/main.py`
  - Validate JSON structure matches expected schema
  - Verify all required fields are present: `db`, `root`

### 2. JSON Schema Validation
Validate the output JSON structure:
```json
{
  "db": {
    "<dist_name>": {
      "srcs": {
        "<module_path>": ["file1.py", "file2.py"]
      },
      "deps": ["dep1", "dep2"],
      "python_version": "3.11|3.12|3.13",
      "python_platform": "linux|macosx|windows"
    }
  },
  "root": "/absolute/path/to/workspace"
}
```

### 3. Multi-File Query Tests
- **Test Multiple Files**:
  - Command: `python3 tools/pyrefly_bazel_query.py --file my_project/main.py --file libs/common/formatters.py`
  - Verify all relevant distributions are included
  - Ensure dependencies are correctly resolved

### 4. Dependency Resolution Tests
- **Test Transitive Dependencies**: Verify that dependencies between packages are correctly identified
- **Test Self-Dependencies**: Ensure packages that depend on themselves are handled correctly
- **Test External Dependencies**: Validate handling of third-party dependencies (if any)

### 5. Module Path Resolution Tests
- **Test py_library Modules**: Verify full dotted import paths (e.g., "click.core", "libs.common.formatters")
- **Test py_binary Modules**: Verify basename resolution (e.g., "main" for main.py)
- **Test Package Init Files**: Ensure __init__.py files are correctly mapped to package names

### 6. Error Handling Tests
- **Test Invalid File Path**: 
  - Command: `python3 tools/pyrefly_bazel_query.py --file nonexistent/file.py`
  - Should handle gracefully or provide meaningful error
- **Test No Arguments**:
  - Command: `python3 tools/pyrefly_bazel_query.py`
  - Should return error JSON: `{"error": "No --file arguments provided"}`
- **Test Bazel Warnings**: Ensure tool works despite Bazel warnings about embedded tools

### 7. Platform and Version Tests
- **Test Python Version Detection**: Verify correct Python version is reported (currently 3.13 based on runtime)
- **Test Platform Detection**: Verify correct platform detection (macosx, linux, windows)

### 8. Regression Tests
- **Test Current Project Structure**: Create a snapshot test of the current project output
- **Test Against Known Good Output**: Compare against a known working state

## Expected Test Files

### Current Project Expected Output (for regression testing)
Based on current structure, expect distributions:
- `colorama`: modules `colorama`, `colorama.ansi`
- `click`: modules `click`, `click.core` (depends on colorama)
- `libs`: modules `libs.common`, `libs.common.formatters`, `libs.common.parsers` (depends on colorama)
- `my_project`: modules including `main` (depends on click, libs, my_project)
- `plugins`: modules `plugins.analyzer`
- `services`: modules under `services.reporting.*`
- `scripts`: modules like `scripts.run_report`

### Test Implementation Notes
- Use `subprocess` to call the actual script
- Parse JSON output and validate structure
- Use `pytest` framework for test organization
- Mock Bazel commands if needed for isolated testing
- Test both success and failure scenarios
- Validate output against JSON schema

### Performance Tests
- **Test Large Project**: Ensure reasonable performance on projects with many files
- **Test Query Efficiency**: Monitor Bazel query execution time

## Implementation Priority
1. Basic functionality and JSON schema validation
2. Error handling tests
3. Dependency resolution tests
4. Regression tests with current project
5. Performance and edge case tests

## Test Environment Setup
- Ensure Bazel is properly configured
- Set up test fixtures with known BUILD.bazel files
- Create helper functions for running queries and validating output
- Set up CI/CD integration for automated testing

## Future Enhancements to Test
- Support for different Python versions in MODULE.bazel
- Support for pip dependencies when enabled
- Support for more complex Bazel configurations
- Performance optimizations for large codebases