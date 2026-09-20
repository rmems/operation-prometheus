"""SPDX expression tokenization outside parentheses."""

from __future__ import annotations

from .license_closure_expr_parens import _paren_depths, _unwrap_outer_parens
from .license_closure_ids_const import EXPRESSION_SPLIT_RE, _MAX_EXPRESSION_DEPTH


def _depths_valid(depths: list[int]) -> bool:
    if any(value < 0 for value in depths):
        return False
    return not depths or depths[-1] == 0


def _top_level_expression_parts(expression: str) -> list[str] | None:
    """Split on AND/OR/WITH that are outside parentheses."""
    depths = _paren_depths(expression)
    if not _depths_valid(depths):
        return None
    parts: list[str] = []
    start = 0
    for match in EXPRESSION_SPLIT_RE.finditer(expression):
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
    return _expression_tokens(inner, depth + 1)


def _piece_tokens(piece: str, operator: str, depth: int) -> list[str] | None:
    token = piece.strip()
    if not token or operator == "WITH":
        return None
    if "(" in token or ")" in token:
        return _nested_piece_tokens(token, depth)
    return [token]


def _piece_operator(parts: list[str], index: int) -> str:
    return parts[index - 1].upper() if index else ""


def _expression_tokens(identifier: str, depth: int = 0) -> list[str] | None:
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
        piece_tokens = _piece_tokens(parts[index], _piece_operator(parts, index), depth)
        if piece_tokens is None:
            return None
        tokens.extend(piece_tokens)
    return tokens
