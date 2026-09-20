"""Parenthesis depth helpers for SPDX expression parsing."""

from __future__ import annotations


def _paren_depths(identifier: str) -> list[int]:
    depth = 0
    depths: list[int] = []
    for char in identifier:
        depth += (char == "(") - (char == ")")
        depths.append(depth)
    return depths


def _parentheses_balanced(identifier: str) -> bool:
    depths = _paren_depths(identifier)
    if not depths:
        return True
    return min(depths) >= 0 and not depths[-1]


def _matching_close_index(identifier: str) -> int | None:
    for index, depth in enumerate(_paren_depths(identifier)):
        if depth < 0:
            return None
        if depth == 0 and identifier[index] == ")":
            return index
    return None


def _outer_wrapped(stripped: str) -> bool:
    if not stripped.startswith("("):
        return False
    if not _parentheses_balanced(stripped):
        return False
    return _matching_close_index(stripped) == len(stripped) - 1


def _unwrap_outer_parens(identifier: str) -> str | None:
    stripped = identifier.strip()
    if not stripped:
        return None
    while _outer_wrapped(stripped):
        stripped = stripped[1:-1].strip()
    if not stripped:
        return None
    return stripped if _parentheses_balanced(stripped) else None
