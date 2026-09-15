"""Fail-closed source-license closure for positive corpus release.

Every released positive trajectory must resolve through frozen source-repository
license evidence, snapshot provenance, and dataset-card disclosure. Missing,
unknown, conflicting, or changed evidence quarantines the row. Quarantined rows
keep their evidence and an explicit reason.

This module does not guess licenses, assess compatibility, or treat this
repository's Apache-2.0 license as a relicense of source-derived material.
Validation is deterministic and uses only caller-supplied frozen evidence.
"""
