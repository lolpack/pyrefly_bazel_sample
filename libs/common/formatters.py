"""Formatting helpers shared across Bazel targets."""

from colorama import color_text
from colorama.ansi import green


def format_greeting(message: str) -> str:
    """Wrap the message in a predictable color sequence."""
    return color_text(green(message), "yellow")
