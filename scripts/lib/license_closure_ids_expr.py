"""SPDX expression parsing and license-family classification."""

from __future__ import annotations

from typing import Any

from .license_closure_ids_const import (
    CLOSED_FAMILIES,
    EXPRESSION_SPLIT_RE,
    LICENSE_REF_RE,
    SPDX_LICENSE_IDS,
    UNKNOWN_LICENSE_IDS,
    _MAX_EXPRESSION_DEPTH,
)
from .license_closure_expr_parens import (
    _paren_depths,
    _unwrap_outer_parens,
)


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


def _depths_valid(depths: list[int]) -> bool:
    if any(value < 0 for value in depths):
        return False
    return not depths or depths[-1] == 0


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


def _expression_tokens(identifier: str, depth: int = 0) -> list[str] | None:
    if depth >= _MAX_EXPRESSION_DEPTH:
        return None
    stripped = identifier.strip()
    if not stripped:
        return []
    unwrapped = _unwrap_outer_parens(stripped)
    if unwrapped is None:
        return None
    parts = _top_level_expression_parts(unwrapped)
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


def classify_license_family(
    identifier: str | None, *, has_custom_evidence: bool = False
) -> str:
    """Classify a declared identifier without guessing a replacement license."""
    tokens = _expression_tokens(identifier) if identifier is not None else None
    if tokens is None:
        return "unknown" if identifier is not None else "missing"
    if not tokens:
        return "missing"
    return _token_family(tokens, has_custom_evidence)


def _license_token_known(token: str) -> bool:
    return token in SPDX_LICENSE_IDS or LICENSE_REF_RE.fullmatch(token) is not None


def _ref_family(tokens: list[str], has_custom_evidence: bool) -> str:
    if not any(LICENSE_REF_RE.fullmatch(token) for token in tokens):
        return "unknown"
    if has_custom_evidence and all(_license_token_known(token) for token in tokens):
        return "custom"
    return "unknown"


def _token_family(tokens: list[str], has_custom_evidence: bool) -> str:
    if any(token.upper() in UNKNOWN_LICENSE_IDS for token in tokens):
        return "unknown"
    if all(token in SPDX_LICENSE_IDS for token in tokens):
        return "spdx"
    return _ref_family(tokens, has_custom_evidence)


def _closed_release_family(
    identifier: Any,
    declared_family: Any,
    *,
    has_custom_evidence: bool = False,
) -> bool:
    family = classify_license_family(
        identifier, has_custom_evidence=has_custom_evidence
    )
    return family in CLOSED_FAMILIES and family == declared_family
