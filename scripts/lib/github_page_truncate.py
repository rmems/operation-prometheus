"""Detect truncated GitHub list/search pages."""

from __future__ import annotations

from typing import Any

from .github_client import _parse_next_link


def infer_truncated(kind: str, body: Any, headers: dict[str, str]) -> bool:
    if not isinstance(body, dict):
        return False
    if body.get("incomplete_results") is True:
        return True
    if kind != "checks":
        return False
    return _truncated_checks(body, headers)


def _truncated_checks(body: dict[str, Any], headers: dict[str, str]) -> bool:
    if not _checks_short_of_total(body):
        return False
    if _parse_next_link(headers.get("link") or ""):
        return False
    return True


def _checks_short_of_total(body: dict[str, Any]) -> bool:
    total = body.get("total_count")
    runs = body.get("check_runs")
    if not isinstance(total, int):
        return False
    if not isinstance(runs, list):
        return False
    return total > len(runs)
