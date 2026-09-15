"""License identifiers, families, and classification for source-license closure."""

from __future__ import annotations

import re
from typing import Any

SCHEMA_VERSION = "license_closure_manifest_v1"
FORGE_LICENSE = "Apache-2.0"
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
GIT_OID_RE = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
LICENSE_REF_RE = re.compile(r"^LicenseRef-[A-Za-z0-9.-]+$")
EXPRESSION_SPLIT_RE = re.compile(r"\s+(AND|OR|WITH)\s+", re.IGNORECASE)
MARKDOWN_LICENSE_SECTION_RE = re.compile(
    r"^##\s+License\s*/\s*provenance\s*$",
    re.IGNORECASE | re.MULTILINE,
)

CLOSED_FAMILIES = frozenset({"spdx", "custom"})
LICENSE_FAMILIES = frozenset({"spdx", "custom", "missing", "unknown"})
UNRESOLVED_REASONS = (
    "source_license_missing",
    "source_license_unknown",
    "source_license_changed",
    "source_license_conflict",
    "snapshot_provenance_missing",
    "card_disclosure_missing",
    "declarations_disagree",
    "forge_license_substitution",
    "source_license_unresolved",
)

# Frozen SPDX identifiers. Unknown IDs fail closed instead of being guessed.
# Includes current SPDX ids and the deprecated GitHub license-API spellings.
SPDX_LICENSE_IDS = frozenset(
    {
        "0BSD",
        "AFL-3.0",
        "AGPL-3.0",
        "AGPL-3.0-only",
        "AGPL-3.0-or-later",
        "Apache-2.0",
        "Artistic-2.0",
        "BlueOak-1.0.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "BSD-3-Clause-Clear",
        "BSD-4-Clause",
        "BSL-1.0",
        "CC-BY-4.0",
        "CC-BY-SA-4.0",
        "CC0-1.0",
        "CDDL-1.0",
        "ECL-2.0",
        "EPL-1.0",
        "EPL-2.0",
        "EUPL-1.1",
        "EUPL-1.2",
        "GPL-2.0",
        "GPL-2.0-only",
        "GPL-2.0-or-later",
        "GPL-3.0",
        "GPL-3.0-only",
        "GPL-3.0-or-later",
        "ISC",
        "LGPL-2.1",
        "LGPL-2.1-only",
        "LGPL-2.1-or-later",
        "LGPL-3.0",
        "LGPL-3.0-only",
        "LGPL-3.0-or-later",
        "LPPL-1.3c",
        "MIT",
        "MIT-0",
        "MPL-2.0",
        "MS-PL",
        "MulanPSL-2.0",
        "NCSA",
        "OFL-1.1",
        "OSL-3.0",
        "PostgreSQL",
        "Python-2.0",
        "Unlicense",
        "UPL-1.0",
        "WTFPL",
        "Zlib",
    }
)
UNKNOWN_LICENSE_IDS = frozenset(
    {
        "NOASSERTION",
        "NONE",
        "OTHER",
        "UNKNOWN",
        "UNLICENSED",
        "SEE LICENSE",
        "SEE-LICENSE",
    }
)


def _text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _sha256_or_none(value: Any) -> str | None:
    text = _text(value).lower()
    if SHA256_RE.fullmatch(text):
        return text
    return None


def normalize_license_id(value: Any) -> str | None:
    """Return a trimmed license identifier, or None when absent/non-string."""
    if isinstance(value, dict):
        for key in ("spdx_id", "id", "license"):
            found = normalize_license_id(value.get(key))
            if found is not None:
                return found
        return None
    text = _text(value)
    return text or None


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


def _expression_tokens(identifier: str) -> list[str] | None:
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
            nested = _expression_tokens(inner)
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


def _same_license(left: str | None, right: str | None) -> bool:
    if left is None or right is None:
        return False
    return left.casefold() == right.casefold()


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
