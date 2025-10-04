"""Helpers to produce formatted reports."""

from libs.common.formatters import format_greeting
from libs.common.parsers import normalize_name
from .metrics import average_score


def build_report(subject: str) -> str:
    """Generate a formatted report banner for the provided subject."""
    normalized = normalize_name(subject)
    score = average_score([len(normalized) or 1, len(subject)])
    message = f"Report[{score:.2f}] for {normalized}"
    return format_greeting(message)
