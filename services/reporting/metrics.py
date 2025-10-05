"""Simple metrics helpers."""

from __future__ import annotations
from typing import Iterable


def average_score(values: Iterable[float]) -> float:
    """Return an average score, guarding against division by zero."""
    values = list(values)
    if not values:
        return 0.0
    return sum(values) / len(values)
