"""Fail-closed source-license closure for positive corpus release.

Every released positive trajectory must resolve through frozen source-repository
license evidence, snapshot provenance, and dataset-card disclosure. Missing,
unknown, conflicting, or changed evidence quarantines the row. Quarantined rows
keep their evidence and an explicit reason.

This module does not guess licenses, assess compatibility, or treat this
repository's Apache-2.0 license as a relicense of source-derived material.
Validation is deterministic and uses only caller-supplied frozen evidence.

Facade module: identifiers live in ``license_closure_ids``, inventory maps in
``license_closure_inventory``, pull-request provenance in ``license_closure_pr``,
evaluation in ``license_closure_eval``, and report assembly in
``license_closure_report``.
"""

from __future__ import annotations

from .license_closure_ids import SCHEMA_VERSION, classify_license_family
from .license_closure_inventory import (
    evidence_digest,
    inventory_row_source_hash,
    license_evidence_payload,
    source_provenance_digest,
)
from .license_closure_pr import pr_inventory_row_source_hash
from .license_closure_report import (
    assert_released_positives_are_closed,
    build_license_closure_report,
    released_positive_ids,
    validate_positive_release,
)

__all__ = [
    "SCHEMA_VERSION",
    "assert_released_positives_are_closed",
    "build_license_closure_report",
    "classify_license_family",
    "evidence_digest",
    "inventory_row_source_hash",
    "license_evidence_payload",
    "pr_inventory_row_source_hash",
    "released_positive_ids",
    "source_provenance_digest",
    "validate_positive_release",
]
