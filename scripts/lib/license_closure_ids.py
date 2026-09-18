"""License identifiers, families, and classification for source-license closure."""

from __future__ import annotations

from .license_closure_ids_const import (
    CLOSED_FAMILIES,
    EXPRESSION_SPLIT_RE,
    FORGE_LICENSE,
    GIT_OID_RE,
    LICENSE_FAMILIES,
    LICENSE_REF_RE,
    MARKDOWN_LICENSE_SECTION_RE,
    MARKDOWN_SECTION_BOUNDARY_RE,
    SCHEMA_VERSION,
    SHA256_RE,
    SPDX_LICENSE_IDS,
    UNKNOWN_LICENSE_IDS,
    UNRESOLVED_REASONS,
    _MAX_EXPRESSION_DEPTH,
    _same_license,
    _sha256_or_none,
    _text,
    normalize_license_id,
)
from .license_closure_ids_expr import _closed_release_family, classify_license_family

__all__ = [
    "CLOSED_FAMILIES",
    "EXPRESSION_SPLIT_RE",
    "FORGE_LICENSE",
    "GIT_OID_RE",
    "LICENSE_FAMILIES",
    "LICENSE_REF_RE",
    "MARKDOWN_LICENSE_SECTION_RE",
    "MARKDOWN_SECTION_BOUNDARY_RE",
    "SCHEMA_VERSION",
    "SHA256_RE",
    "SPDX_LICENSE_IDS",
    "UNKNOWN_LICENSE_IDS",
    "UNRESOLVED_REASONS",
    "_MAX_EXPRESSION_DEPTH",
    "_closed_release_family",
    "_same_license",
    "_sha256_or_none",
    "_text",
    "classify_license_family",
    "normalize_license_id",
]
