"""Shared libraries for sample Bazel targets."""

from .formatters import format_greeting
from .parsers import normalize_name

__all__ = ["format_greeting", "normalize_name"]
