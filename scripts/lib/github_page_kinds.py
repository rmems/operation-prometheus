"""Map GitHub REST URLs to cassette page kinds."""

from __future__ import annotations

import re
import urllib.parse

PAGE_KINDS = (
    "pull",
    "issue",
    "comment",
    "review",
    "commit",
    "checks",
    "status",
    "file",
    "diff",
    "other",
)

_KIND_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"/commits/[^/]+/check-runs(?:\?|$)"), "checks"),
    (re.compile(r"/commits/[^/]+/status(?:\?|$)"), "status"),
    (re.compile(r"/pulls/\d+/files(?:\?|$)"), "file"),
    (re.compile(r"/pulls/\d+/comments(?:\?|$)"), "comment"),
    (re.compile(r"/issues/\d+/comments(?:\?|$)"), "comment"),
    (re.compile(r"/pulls/\d+/reviews(?:\?|$)"), "review"),
    (re.compile(r"/pulls/\d+/commits(?:\?|$)"), "commit"),
    (re.compile(r"/repos/[^/]+/[^/]+/commits/[^/?]+(?:\?|$)"), "commit"),
    (re.compile(r"/pulls/\d+(?:\?|$)"), "pull"),
    (re.compile(r"/issues/\d+(?:\?|$)"), "issue"),
)


def classify_page_kind(url: str, accept: str = "") -> str:
    """Map a GitHub REST URL (and optional Accept) to a page kind."""
    accept_l = accept.lower()
    if "diff" in accept_l or "patch" in accept_l:
        return "diff"
    return _kind_from_path(urllib.parse.urlsplit(url).path)


def _kind_from_path(path: str) -> str:
    for pattern, kind in _KIND_RULES:
        if pattern.search(path):
            return kind
    return "other"
