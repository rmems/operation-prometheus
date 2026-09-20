"""Parenthesis helpers for SPDX expression parsing."""

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
    return not depths or (min(depths) >= 0 and not depths[-1])


def _matching_close_index(identifier: str) -> int | None:
    for index, depth in enumerate(_paren_depths(identifier)):
        if depth < 0:
            return None
        if depth == 0 and identifier[index] == ")":
            return index
    return None


def _unwrap_outer_parens(identifier: str) -> str | None:
    stripped = identifier.strip()
    if not stripped or not _parentheses_balanced(stripped):
        return None
    while stripped.startswith("("):
        if _matching_close_index(stripped) != len(stripped) - 1:
            break
        stripped = stripped[1:-1].strip()
        if not stripped or not _parentheses_balanced(stripped):
            return None
    return stripped
