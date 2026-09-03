"""Deterministic eligibility-ledger construction from a frozen source snapshot.

Facade module: the implementation is split into responsibility-focused sibling
modules (``eligibility_common``, ``eligibility_quality``, ``eligibility_classification``,
``eligibility_lineage``, ``eligibility_duplicates``, ``eligibility_baseline``,
``eligibility_repositories``, ``eligibility_existing``, ``eligibility_artifacts``,
``eligibility_render``). Every name previously importable from here still is.
"""

from __future__ import annotations

from .eligibility_artifacts import build_eligibility_artifacts
from .eligibility_baseline import (
    _baseline_counts as _baseline_counts,
    _post_cutoff_evidence as _post_cutoff_evidence,
    build_baseline_report,
)
from .eligibility_classification import (
    _TASK_PATTERNS as _TASK_PATTERNS,
    _automatic_state as _automatic_state,
    _override_map as _override_map,
    infer_task_family,
)
from .eligibility_common import (
    LEDGER_SCHEMA_VERSION,
    LEDGER_STATES,
    MANIFEST_SCHEMA_VERSION,
    REPOSITORY_SCHEMA_VERSION,
    _parse_time as _parse_time,
    _source_ref as _source_ref,
    candidate_id,
)
from .eligibility_duplicates import (
    _STOP_TOKENS as _STOP_TOKENS,
    _TOKEN_RE as _TOKEN_RE,
    _duplicate_records as _duplicate_records,
    _normalized_exact_title as _normalized_exact_title,
    _title_tokens as _title_tokens,
)
from .eligibility_existing import _load_existing_rows as _load_existing_rows
from .eligibility_lineage import (
    _ISSUE_SCOPED_BARE_REF as _ISSUE_SCOPED_BARE_REF,
    _PR_REF_PATTERN as _PR_REF_PATTERN,
    _REVERT_REF as _REVERT_REF,
    _SUPERSEDE_REF as _SUPERSEDE_REF,
    _lineage as _lineage,
    _multi_pr_lineage as _multi_pr_lineage,
)
from .eligibility_quality import (
    QUALITY_ASSESSMENTS,
    QUALITY_DIMENSIONS,
    _quality as _quality,
    assess_quality,
)
from .eligibility_render import render_artifacts, render_json, render_jsonl
from .eligibility_repositories import (
    _apply_repository_aliases as _apply_repository_aliases,
    _repository_row as _repository_row,
)

__all__ = [
    "LEDGER_SCHEMA_VERSION",
    "LEDGER_STATES",
    "MANIFEST_SCHEMA_VERSION",
    "QUALITY_ASSESSMENTS",
    "QUALITY_DIMENSIONS",
    "REPOSITORY_SCHEMA_VERSION",
    "_ISSUE_SCOPED_BARE_REF",
    "_PR_REF_PATTERN",
    "_REVERT_REF",
    "_STOP_TOKENS",
    "_SUPERSEDE_REF",
    "_TASK_PATTERNS",
    "_TOKEN_RE",
    "_apply_repository_aliases",
    "_automatic_state",
    "_baseline_counts",
    "_duplicate_records",
    "_lineage",
    "_load_existing_rows",
    "_multi_pr_lineage",
    "_normalized_exact_title",
    "_override_map",
    "_parse_time",
    "_post_cutoff_evidence",
    "_quality",
    "_repository_row",
    "_source_ref",
    "_title_tokens",
    "assess_quality",
    "build_baseline_report",
    "build_eligibility_artifacts",
    "candidate_id",
    "infer_task_family",
    "render_artifacts",
    "render_json",
    "render_jsonl",
]
