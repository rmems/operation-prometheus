"""License-family lookup for tokenized SPDX expressions."""

from __future__ import annotations

from .license_closure_ids_const import (
    LICENSE_REF_RE,
    SPDX_LICENSE_IDS,
    UNKNOWN_LICENSE_IDS,
)


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
