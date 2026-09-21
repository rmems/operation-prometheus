"""SPDX expression tokenization with bounded parenthesis nesting."""

from __future__ import annotations

import re

_EXPRESSION_SPLIT_RE = re.compile(r"\s+(AND|OR|WITH)\s+", re.IGNORECASE)
_MAX_EXPRESSION_DEPTH = 32


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


def _unwrap_outer_parens(identifier: str) -> str | None:
    stripped = identifier.strip()
    if not stripped:
        return None
    while (
        stripped.startswith("(")
        and _parentheses_balanced(stripped)
        and _matching_close_index(stripped) == len(stripped) - 1
    ):
        stripped = stripped[1:-1].strip()
    if not stripped:
        return None
    return stripped if _parentheses_balanced(stripped) else None


def _top_level_expression_parts(expression: str) -> list[str] | None:
    """Split on AND/OR/WITH that are outside parentheses."""
    depths = _paren_depths(expression)
    if any(value < 0 for value in depths) or (depths and depths[-1] != 0):
        return None
    parts: list[str] = []
    start = 0
    for match in _EXPRESSION_SPLIT_RE.finditer(expression):
        if any(depths[i] for i in range(match.start(), match.end())):
            continue
        parts.append(expression[start : match.start()].strip())
        parts.append(match.group(1).upper())
        start = match.end()
    parts.append(expression[start:].strip())
    return parts


def _nested_piece_tokens(token: str, depth: int) -> list[str] | None:
    if not (token.startswith("(") and token.endswith(")")):
        return None
    inner = _unwrap_outer_parens(token)
    if inner is None or inner == token:
        return None
    return expression_tokens(inner, depth + 1)


def _piece_tokens(piece: str, operator: str, depth: int) -> list[str] | None:
    token = piece.strip()
    if not token or operator == "WITH":
        return None
    if "(" in token or ")" in token:
        return _nested_piece_tokens(token, depth)
    return [token]


def expression_tokens(identifier: str, depth: int = 0) -> list[str] | None:
    """Flatten an SPDX expression to license tokens, or None if unparseable."""
    if depth >= _MAX_EXPRESSION_DEPTH:
        return None
    stripped = identifier.strip()
    if not stripped:
        return []
    unwrapped = _unwrap_outer_parens(stripped)
    parts = None if unwrapped is None else _top_level_expression_parts(unwrapped)
    if parts is None:
        return None
    tokens: list[str] = []
    for index in range(0, len(parts), 2):
        operator = parts[index - 1].upper() if index else ""
        piece_tokens = _piece_tokens(parts[index], operator, depth)
        if piece_tokens is None:
            return None
        tokens.extend(piece_tokens)
    return tokens
