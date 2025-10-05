"""Analyzer helpers built on top of the reporting service."""

from typing import Iterable

from services.reporting import average_score, build_report


def summarize(subjects: Iterable[str]) -> str:
    """Build a compact summary for the provided subjects."""
    reports = [build_report(subject) for subject in subjects]
    score = average_score(len(subject) for subject in subjects)
    return f"Summary[{score:.1f}] -> {' | '.join(reports)}"
