"""Formatting helpers for :mod:`my_project`."""

from libs.common.formatters import format_greeting


def stylize_message(message: str) -> str:
    """Apply shared formatting rules to a message string."""
    return format_greeting(message)
