"""Lossless pr_trajectory_v0 → trajectory-v1 envelope migration.

Maps only values present in the source record. Missing evidence is recorded as
unavailable or the record is refused; timestamps, OIDs, actors, and events are
never invented. Admitted output is schema-valid v1 that also passes
``validate_jsonl --strict-policy``.
"""

from __future__ import annotations

from .migrate_v0_constants import MIGRATION_TOOL_VERSION
from .migrate_v0_io import atomic_write_text, migrate_files, migrate_jsonl
from .migrate_v0_mapping import canonical_dumps, source_digest
from .migrate_v0_record import migrate_record
from .migrate_v0_text import resolved_same

__all__ = [
    "MIGRATION_TOOL_VERSION",
    "atomic_write_text",
    "canonical_dumps",
    "migrate_files",
    "migrate_jsonl",
    "migrate_record",
    "resolved_same",
    "source_digest",
]
