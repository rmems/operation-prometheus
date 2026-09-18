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
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                return False
            depth -= 1
    return depth == 0


def _matching_close_index(identifier: str) -> int | None:
    depth = 0
    for index, char in enumerate(identifier):
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                return None
            depth -= 1
            if depth == 0:
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


def _top_level_expression_parts(expression: str) -> list[str] | None:
    """Split on AND/OR/WITH that are outside parentheses."""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    index = 0
    length = len(expression)
    while index < length:
        char = expression[index]
        if char == "(":
            depth += 1
            buf.append(char)
            index += 1
            continue
        if char == ")":
            if depth == 0:
                return None
            depth -= 1
            buf.append(char)
            index += 1
            continue
        if depth == 0:
            match = EXPRESSION_SPLIT_RE.match(expression, index)
            if match is not None:
                parts.append("".join(buf).strip())
                parts.append(match.group(1).upper())
                buf = []
                index = match.end()
                continue
        buf.append(char)
        index += 1
    if depth != 0:
        return None
    parts.append("".join(buf).strip())
    return parts


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
        token = piece.strip()
        if not token:
            return None
        operator = parts[index - 1].upper() if index else ""
        if operator == "WITH":
            return None
        if "(" in token or ")" in token:
            if not (token.startswith("(") and token.endswith(")")):
                return None
            inner = _unwrap_outer_parens(token)
            if inner is None or inner == token:
                return None
            nested = _expression_tokens(inner, depth + 1)
            if nested is None:
                return None
            tokens.extend(nested)
            continue
        tokens.append(token)
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
    upper_tokens = [token.upper() for token in tokens]
    if any(token in UNKNOWN_LICENSE_IDS for token in upper_tokens):
        return "unknown"
    if any(LICENSE_REF_RE.fullmatch(token) for token in tokens):
        if has_custom_evidence and all(
            token in SPDX_LICENSE_IDS or LICENSE_REF_RE.fullmatch(token)
            for token in tokens
        ):
            return "custom"
        return "unknown"
    if all(token in SPDX_LICENSE_IDS for token in tokens):
        return "spdx"
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
