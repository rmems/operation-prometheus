"""Sanitized GitHub REST page cassettes for offline collector replay.

Recorded envelopes keep pagination, ETag, and rate-limit metadata while
dropping credentials, cookies, and unstable transport headers. Replay is
strictly ordered and GET-only — the live collector remains read-only.
"""

from __future__ import annotations

from .github_page_cassette import (
    CASSETTE_SCHEMA_VERSION,
    cassette_dict,
    dumps_cassette,
    load_cassette,
    mark_duplicates,
    scan_cassette_secrets,
    validate_cassette,
    write_cassette,
)
from .github_page_envelope import PageCapture, build_page_envelope, envelope_replay_bytes
from .github_page_kinds import PAGE_KINDS, classify_page_kind
from .github_page_sanitize import (
    request_accept,
    request_identity,
    sanitize_headers,
    sanitize_link_header,
    sanitize_url,
)
from .github_page_transport import (
    RecordingOpener,
    ReplayOpener,
    ReplayOptions,
    attach_page_recorder,
    replay_github_client,
)

__all__ = [
    "CASSETTE_SCHEMA_VERSION",
    "PAGE_KINDS",
    "PageCapture",
    "RecordingOpener",
    "ReplayOpener",
    "ReplayOptions",
    "attach_page_recorder",
    "build_page_envelope",
    "cassette_dict",
    "classify_page_kind",
    "dumps_cassette",
    "envelope_replay_bytes",
    "load_cassette",
    "mark_duplicates",
    "replay_github_client",
    "request_accept",
    "request_identity",
    "scan_cassette_secrets",
    "sanitize_headers",
    "sanitize_link_header",
    "sanitize_url",
    "validate_cassette",
    "write_cassette",
]
