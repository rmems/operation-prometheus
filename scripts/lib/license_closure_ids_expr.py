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

def _parentheses_balanced(identifier: str) -> bool:
    depth = 0
    for char in identifier:
        depth += (char == "(") - (char == ")")
        if depth < 0:
            return False
    return depth == 0


def _matching_close_index(identifier: str) -> int | None:
    depth = 0
    for index, char in enumerate(identifier):
        depth += (char == "(") - (char == ")")
        if depth < 0:
            return None
        if char == ")" and depth == 0:
            return index
    return None


def _unwrap_outer_parens(identifier: str) -> str | None:
    stripped = identifier.strip()
    if not stripped or not _parentheses_balanced(stripped):
        return None
    while stripped.startswith("("):
        close = _matching_close_index(stripped)
        if close is None or close != len(stripped) - 1:
            break
        inner = stripped[1:-1].strip()
        if not inner or not _parentheses_balanced(inner):
            return None
        stripped = inner
    return stripped


def _expression_separator(expression: str, index: int, depth: int):
    if depth != 0:
        return None
    return EXPRESSION_SPLIT_RE.match(expression, index)


def _top_level_expression_parts(expression: str) -> list[str] | None:
    """Split on AND/OR/WITH that are outside parentheses."""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    index = 0
    length = len(expression)
    while index < length:
        match = _expression_separator(expression, index, depth)
        if match is not None:
            parts.append("".join(buf).strip())
            parts.append(match.group(1).upper())
            buf = []
            index = match.end()
            continue
        char = expression[index]
        buf.append(char)
        depth += (char == "(") - (char == ")")
        if depth < 0:
            return None
        index += 1
    if depth != 0:
        return None
    parts.append("".join(buf).strip())
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
    for index, piece in enumerate(parts):
        if index % 2 == 1:
            continue
        operator = parts[index - 1].upper() if index else ""
        piece_tokens = _piece_tokens(piece, operator, depth)
        if piece_tokens is None:
            return None
        tokens.extend(piece_tokens)
    return tokens


def classify_license_family(
    identifier: str | None, *, has_custom_evidence: bool = False
) -> str:
    """Classify a declared identifier without guessing a replacement license."""
    if identifier is None:
        return "missing"
    tokens = _expression_tokens(identifier)
    if tokens is None:
        return "unknown"
    if not tokens:
        return "missing"
    return _token_family(tokens, has_custom_evidence)


def _license_token_known(token: str) -> bool:
    return token in SPDX_LICENSE_IDS or LICENSE_REF_RE.fullmatch(token) is not None


def _token_family(tokens: list[str], has_custom_evidence: bool) -> str:
    if any(token.upper() in UNKNOWN_LICENSE_IDS for token in tokens):
        return "unknown"
    if all(token in SPDX_LICENSE_IDS for token in tokens):
        return "spdx"
    if not any(LICENSE_REF_RE.fullmatch(token) for token in tokens):
        return "unknown"
    if has_custom_evidence and all(_license_token_known(token) for token in tokens):
        return "custom"
    return "unknown"


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
