"""Shared primitives for source-inventory collection.

Kept dependency-free (stdlib only) so both the repository and pull-request
collection modules — and the eligibility ledger — can build on them without
import cycles.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, NamedTuple


def canonical_json_bytes(value: Any) -> bytes:
    """Return the canonical UTF-8 representation used for source hashes."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


class _Page(NamedTuple):
    """Everything known about one collected API page."""

    scope: str
    response: Any
    item_count: int
    page_index: int
    has_next_page: bool
    headers: dict[str, str]
    owner: str | None = None
    repository_id: str | None = None
    cursor: str | None = None
    next_cursor: str | None = None
    total_count: int | None = None


def _page_evidence(page: _Page) -> dict[str, Any]:
    hashable_response = page.response
    if isinstance(page.response, dict) and "rateLimit" in page.response:
        hashable_response = dict(page.response)
        hashable_response.pop("rateLimit", None)
    return {
        "scope": page.scope,
        "owner": page.owner,
        "repository_id": page.repository_id,
        "page_index": page.page_index,
        "cursor": page.cursor,
        "next_cursor": page.next_cursor,
        "item_count": page.item_count,
        "total_count": page.total_count,
        "has_next_page": page.has_next_page,
        "server_date": page.headers.get("date"),
        "response_sha256": sha256_json(hashable_response),
    }
