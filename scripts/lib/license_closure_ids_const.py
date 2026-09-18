"""License identifiers, families, and frozen SPDX constants."""

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
    r"^ {0,3}##[ \t]+License[ \t]+/[ \t]*provenance(?:[ \t]+#+)?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
MARKDOWN_SECTION_BOUNDARY_RE = re.compile(
    r"^ {0,3}#{1,2}(?:\s|$)|^ {0,3}\S[^\n]*\n {0,3}(?:=+|-+)[ \t]*$",
    re.MULTILINE,
)
_MAX_EXPRESSION_DEPTH = 32

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



def _same_license(left: str | None, right: str | None) -> bool:
    if left is None or right is None:
        return False
    return left.casefold() == right.casefold()


