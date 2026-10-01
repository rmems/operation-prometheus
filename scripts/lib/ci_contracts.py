"""Shared helpers for trajectory and consumer CI contracts."""

from __future__ import annotations

from .ci_io import JSONL_DIR, ROOT, load_jsonl, record_identity, sha256_file
from .ci_policy import (
    blank_license_policy_errors,
    is_real_check_run_detail,
    silent_truncation_errors,
    unique_artifact_errors,
    unique_event_errors,
    validation_evidence_errors,
)
from .ci_private_refs import iter_uri_fields, private_reference_errors

__all__ = [
    "JSONL_DIR",
    "ROOT",
    "blank_license_policy_errors",
    "is_real_check_run_detail",
    "iter_uri_fields",
    "load_jsonl",
    "private_reference_errors",
    "record_identity",
    "sha256_file",
    "silent_truncation_errors",
    "unique_artifact_errors",
    "unique_event_errors",
    "validation_evidence_errors",
]
