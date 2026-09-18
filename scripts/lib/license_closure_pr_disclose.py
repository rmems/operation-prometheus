"""License-section visibility and identifier disclosure."""

from __future__ import annotations

import re

from .license_closure_ids import MARKDOWN_LICENSE_SECTION_RE, MARKDOWN_SECTION_BOUNDARY_RE
from .license_closure_pr_html import (
    FENCE_OPEN_RE,
    HTML_COMMENT_RE,
    HTML_TAG_RE,
    MARKDOWN_REFERENCE_LINK_RE,
    _strip_non_rendered_html,
)
from .license_closure_pr_links import _strip_inline_links, _strip_reference_definitions

def _strip_fenced_code(markdown: str) -> str:
    kept: list[str] = []
    fence_char: str | None = None
    fence_len = 0
    for line in markdown.splitlines(keepends=True):
        if fence_char is None:
            match = FENCE_OPEN_RE.match(line)
            if match is not None:
                marker = match.group(2)
                fence_char = marker[0]
                fence_len = len(marker)
                continue
            kept.append(line)
            continue
        stripped = line.rstrip("\n")
        leading = len(stripped) - len(stripped.lstrip(" "))
        rest = stripped.lstrip(" ")
        if leading <= 3 and rest.startswith(fence_char * fence_len):
            after = rest[fence_len:].lstrip(fence_char)
            if after.strip() == "":
                fence_char = None
                fence_len = 0
                continue
    return "".join(kept)


def _markdown_license_section(markdown: str) -> str | None:
    match = MARKDOWN_LICENSE_SECTION_RE.search(markdown)
    if match is None:
        return None
    rest = markdown[match.end() :]
    next_heading = MARKDOWN_SECTION_BOUNDARY_RE.search(rest)
    if next_heading is None:
        return rest
    return rest[: next_heading.start()]


def _visible_markdown_text(markdown: str) -> str:
    visible = HTML_COMMENT_RE.sub("", markdown)
    visible = _strip_reference_definitions(visible)
    visible = _strip_inline_links(visible)
    visible = MARKDOWN_REFERENCE_LINK_RE.sub(r"\1", visible)
    visible = _strip_non_rendered_html(visible)
    return HTML_TAG_RE.sub("", visible)


def _strip_hidden_markup(markdown: str) -> str:
    visible = HTML_COMMENT_RE.sub("", markdown)
    visible = _strip_inline_links(visible, keep_openers=True)
    return _strip_non_rendered_html(visible)


def _markdown_discloses(markdown: str | None, identifier: str | None) -> bool:
    if markdown is None:
        return True
    section = _markdown_license_section(
        _strip_hidden_markup(_strip_fenced_code(markdown))
    )
    if section is None or not identifier:
        return False
    visible = _visible_markdown_text(section)
    pattern = r"(?<![A-Za-z0-9.+-])" + re.escape(identifier) + r"(?![A-Za-z0-9.+-])"
    return re.search(pattern, visible, flags=re.IGNORECASE) is not None
