"""Parsing helpers shared across Bazel targets."""


def normalize_name(raw: str) -> str:
    """Normalize a raw identifier into title-case."""
    return " ".join(part.title() for part in raw.strip().split())
