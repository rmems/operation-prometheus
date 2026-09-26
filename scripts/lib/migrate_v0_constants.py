"""Constants for lossless v0-to-v1 trajectory migration."""

from __future__ import annotations

import re

MIGRATION_TOOL_VERSION = "migrate-v0-to-v1/0.2.1"
V1_SCHEMA_VERSIONS = frozenset({"1", "1.0", "v1"})
SOURCE_SCHEMA = "pr_trajectory_v0"
COLLECTION_POLICY = "migrated-from-pr_trajectory_v0"
PROVIDER_ID = "github"
MIGRATION_ACTOR_ID = "operation-prometheus.migrate_v0_to_v1"
IMPORT_EVENT_TYPE = "v0_envelope_import"

OUTCOME_TO_TERMINAL = {
    "merged": "successful",
    "closed": "failed",
    "abandoned": "interrupted",
    "open": "interrupted",
}
UNMAPPABLE_OUTCOMES = frozenset({"superseded"})
TIMESTAMP_KEYS = ("timestamp", "merged_at", "closed_at", "created_at", "updated_at")
TERMINAL_TIMESTAMP_KEYS = {
    "merged": ("timestamp", "merged_at"),
    "closed": ("timestamp", "closed_at"),
    "abandoned": ("timestamp", "closed_at"),
}
OID_FIELD_MAP = (
    ("commit_oid", "commit_oid"),
    ("merge_commit_sha", "commit_oid"),
    ("head_oid", "head_oid"),
    ("head_sha", "head_oid"),
    ("base_oid", "base_oid"),
    ("base_sha", "base_oid"),
    ("tree_oid", "tree_oid"),
    ("before_blob", "before_blob"),
    ("after_blob", "after_blob"),
)
REQUIRED_V0_KEYS = (
    "id",
    "repo",
    "pr_number",
    "source_urls",
    "language",
    "domain",
    "task_type",
    "before_context",
    "patch",
    "validation",
    "outcome",
    "training_use",
)
KNOWN_EVENT_TYPES = frozenset(
    {
        IMPORT_EVENT_TYPE,
        "commit",
        "experiment",
        "misc",
        "review",
        "validation",
        "ci",
        "test",
        "manual",
        "other",
        "patch",
        "issue",
        "pr_outcome",
    }
)
KNOWN_VALIDATION_TYPES = frozenset({"ci", "test", "manual", "review", "other"})
GIT_OID_RE = re.compile(r"^[0-9a-fA-F]{3,64}$")
REPO_RE = re.compile(
    r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?/[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$"
)
SOURCE_URL_RE = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/(pull|issues)/[0-9]+(?:#.*)?$"
)
