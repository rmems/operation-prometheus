"""Rights/license classification for local-model admission.

Consolidated from the license-closure expression parser: tokenizes SPDX-style
``AND``/``OR`` expressions with bounded parenthesis nesting and classifies the
final identifier as ``spdx`` / ``custom`` / ``missing`` / ``unknown`` without
ever guessing a replacement license.
"""

from __future__ import annotations

import re
from typing import Any

LICENSE_REF_RE = re.compile(r"^LicenseRef-[A-Za-z0-9.-]+$")
_EXPRESSION_SPLIT_RE = re.compile(r"\s+(AND|OR|WITH)\s+", re.IGNORECASE)
_MAX_EXPRESSION_DEPTH = 32

CLOSED_FAMILIES = frozenset({"spdx", "custom"})
LICENSE_FAMILIES = frozenset({"spdx", "custom", "missing", "unknown"})

# Frozen SPDX identifiers (incl. deprecated GitHub license-API spellings).
# Unknown ids fail closed instead of being guessed.
SPDX_LICENSE_IDS = frozenset(
    {
        "0BSD", "AFL-3.0", "AGPL-3.0", "AGPL-3.0-only", "AGPL-3.0-or-later",
        "Apache-2.0", "Artistic-2.0", "BlueOak-1.0.0", "BSD-2-Clause",
        "BSD-3-Clause", "BSD-3-Clause-Clear", "BSD-4-Clause", "BSL-1.0",
        "CC-BY-4.0", "CC-BY-SA-4.0", "CC0-1.0", "CDDL-1.0", "ECL-2.0",
        "EPL-1.0", "EPL-2.0", "EUPL-1.1", "EUPL-1.2", "GPL-2.0",
        "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0", "GPL-3.0-only",
        "GPL-3.0-or-later", "ISC", "LGPL-2.1", "LGPL-2.1-only",
        "LGPL-2.1-or-later", "LGPL-3.0", "LGPL-3.0-only", "LGPL-3.0-or-later",
        "LPPL-1.3c", "MIT", "MIT-0", "MPL-2.0", "MS-PL", "MulanPSL-2.0",
        "NCSA", "OFL-1.1", "OSL-3.0", "PostgreSQL", "Python-2.0",
        "Unlicense", "UPL-1.0", "WTFPL", "Zlib",
    }
)
UNKNOWN_LICENSE_IDS = frozenset(
    {"NOASSERTION", "NONE", "OTHER", "UNKNOWN", "UNLICENSED",
     "SEE LICENSE", "SEE-LICENSE"}
)


def normalize_license_id(value: Any) -> str | None:
    """Return a trimmed license identifier, or None when absent/non-string."""
    if isinstance(value, dict):
        for key in ("spdx_id", "id", "license"):
            found = normalize_license_id(value.get(key))
            if found is not None:
                return found
        return None
    if not isinstance(value, str):
        return None
    return value.strip() or None


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


def _unwrap_outer_parens(identifier: str) -> str | None:
    stripped = identifier.strip()
    if not stripped:
        return None
    while stripped.startswith("(") and _parentheses_balanced(stripped):
        depths = _paren_depths(stripped)
        close = next(
            (i for i, d in enumerate(depths) if d == 0 and stripped[i] == ")"),
            None,
        )
        if close != len(stripped) - 1:
            break
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
        operator = parts[index - 1].upper() if index else ""
        token = parts[index].strip()
        if not token or operator == "WITH":
            return None
        if "(" in token or ")" in token:
            inner = _unwrap_outer_parens(token)
            if inner is None or inner == token:
                return None
            piece = _expression_tokens(inner, depth + 1)
            if piece is None:
                return None
            tokens.extend(piece)
        else:
            tokens.append(token)
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
    if any(token.upper() in UNKNOWN_LICENSE_IDS for token in tokens):
        return "unknown"
    if all(token in SPDX_LICENSE_IDS for token in tokens):
        return "spdx"
    if not any(LICENSE_REF_RE.fullmatch(token) for token in tokens):
        return "unknown"
    if has_custom_evidence and all(
        token in SPDX_LICENSE_IDS or LICENSE_REF_RE.fullmatch(token)
        for token in tokens
    ):
        return "custom"
    return "unknown"
