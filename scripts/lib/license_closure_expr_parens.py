"""Expression internals: parentheses, tokenization, and family lookup."""

from __future__ import annotations

from .license_closure_ids_const import (
    EXPRESSION_SPLIT_RE,
    LICENSE_REF_RE,
    SPDX_LICENSE_IDS,
    UNKNOWN_LICENSE_IDS,
    _MAX_EXPRESSION_DEPTH,
)


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
    if not stripped or not _parentheses_balanced(stripped):
        return None
    while stripped.startswith("("):
        if _matching_close_index(stripped) != len(stripped) - 1:
            break
        stripped = stripped[1:-1].strip()
        if not stripped or not _parentheses_balanced(stripped):
            return None
    return stripped


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
