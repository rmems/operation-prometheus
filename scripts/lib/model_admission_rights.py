"""Rights/license classification for local-model admission.

Final SPDX / ``LicenseRef-*`` family classification over tokenized
expressions. Unknown identifiers fail closed instead of being guessed.
Expression tokenization lives in ``model_admission_rights_expr``.
"""

from __future__ import annotations

import re
from typing import Any

from .model_admission_rights_expr import expression_tokens

LICENSE_REF_RE = re.compile(r"^LicenseRef-[A-Za-z0-9.-]+$")

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


def _license_token_known(token: str) -> bool:
    return token in SPDX_LICENSE_IDS or LICENSE_REF_RE.fullmatch(token)


def _ref_family(tokens: list[str], has_custom_evidence: bool) -> str:
    if not any(LICENSE_REF_RE.fullmatch(token) for token in tokens):
        return "unknown"
    if has_custom_evidence and all(
        _license_token_known(token) for token in tokens
    ):
        return "custom"
    return "unknown"


def _token_family(tokens: list[str], has_custom_evidence: bool) -> str:
    if any(token.upper() in UNKNOWN_LICENSE_IDS for token in tokens):
        return "unknown"
    if all(token in SPDX_LICENSE_IDS for token in tokens):
        return "spdx"
    return _ref_family(tokens, has_custom_evidence)


def classify_license_family(
    identifier: str | None, *, has_custom_evidence: bool = False
) -> str:
    """Classify a declared identifier without guessing a replacement license."""
    tokens = expression_tokens(identifier) if identifier is not None else None
    if tokens is None:
        return "unknown" if identifier is not None else "missing"
    if not tokens:
        return "missing"
    return _token_family(tokens, has_custom_evidence)
