"""Shared helpers for trajectory, corpus, consumer, and release CI contracts."""

from __future__ import annotations

from .ci_inventory import (
    candidate_index,
    candidate_reason_errors,
    inventory_file_hash_errors,
    load_inventory_candidates,
    load_inventory_repositories,
    parquet_hash_errors,
)
from .ci_io import (
    INVENTORY_DIR,
    JSONL_DIR,
    MANIFEST_DIR,
    PARQUET_DIR,
    RELEASE_MANIFEST,
    ROOT,
    load_jsonl,
    record_identity,
    sha256_file,
)
from .ci_policy import (
    blank_license_policy_errors,
    is_real_check_run_detail,
    silent_truncation_errors,
    unique_artifact_errors,
    unique_event_errors,
    validation_evidence_errors,
)
from .ci_private_refs import iter_uri_fields, private_reference_errors
from .eligibility_common import LEDGER_STATES

POSITIVE_RELEASE_STATES = frozenset({"included_positive"})
MUTABLE_STATES = frozenset({"watchlist_open"})
MUTABLE_SOURCE_STATES = frozenset({"open"})

__all__ = [
    "INVENTORY_DIR",
    "JSONL_DIR",
    "LEDGER_STATES",
    "MANIFEST_DIR",
    "MUTABLE_SOURCE_STATES",
    "MUTABLE_STATES",
    "PARQUET_DIR",
    "POSITIVE_RELEASE_STATES",
    "RELEASE_MANIFEST",
    "ROOT",
    "blank_license_policy_errors",
    "candidate_index",
    "candidate_reason_errors",
    "inventory_file_hash_errors",
    "is_real_check_run_detail",
    "iter_uri_fields",
    "load_inventory_candidates",
    "load_inventory_repositories",
    "load_jsonl",
    "parquet_hash_errors",
    "private_reference_errors",
    "record_identity",
    "sha256_file",
    "silent_truncation_errors",
    "unique_artifact_errors",
    "unique_event_errors",
    "validation_evidence_errors",
]
