"""Core application logic for the Bazel sample."""

from libs.common.parsers import normalize_name
from my_project.utils.formatting import stylize_message


def greeting(raw_name: str) -> str:
    """Return a formatted greeting for the provided name."""
    cleaned = normalize_name(raw_name)
    return stylize_message(f"Hello {cleaned}!")
