"""Pull-request provenance and markdown disclosure for source-license closure."""

from __future__ import annotations

from .license_closure_pr_md import _markdown_discloses
from .license_closure_pr_oids import (
    _declared_repos,
    _index_pull_requests,
    _pr_inventory_reasons,
    _source_coverage_invalid,
    pr_inventory_row_source_hash,
)

__all__ = [
    "_declared_repos",
    "_index_pull_requests",
    "_markdown_discloses",
    "_pr_inventory_reasons",
    "_source_coverage_invalid",
    "pr_inventory_row_source_hash",
]
