"""Visible HTML text extraction for license-section disclosure."""

from __future__ import annotations

import re
from html.parser import HTMLParser

HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
HTML_TAG_RE = re.compile(r"</?[^>]+>")
_NON_RENDERED_HTML_TAGS = frozenset({"noscript", "script", "style", "template"})
_VOID_HTML_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_BLOCK_HTML_TAGS = frozenset(
    {
        "address",
        "article",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
)
_HIDDEN_STYLE_RE = re.compile(
    r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)\b",
    re.IGNORECASE,
)
MARKDOWN_REFERENCE_DESTINATION_RE = re.compile(r"""^[ \t]*(?:<[^>\n]*>|\S+)\s*$""")
MARKDOWN_REFERENCE_TITLE_RE = re.compile(
    r"""^[ \t]+(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\((?:\\.|[^)\\])*\))\s*$"""
)
MARKDOWN_REFERENCE_LINK_RE = re.compile(r"!?\[([^\]\n]*)\]\[[^\]\n]*\]")
FENCE_OPEN_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})")




class _VisibleHtmlText(HTMLParser):
    """Collect text that would render, skipping hidden and non-rendered HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip: list[str] = []
        self.parts: list[str] = []

    def _hides(self, tag: str, attrs: list[tuple[str, str | None]]) -> bool:
        if tag in _NON_RENDERED_HTML_TAGS:
            return True
        for name, value in attrs:
            folded = name.casefold()
            if folded == "hidden":
                return True
            if folded == "style" and value and _HIDDEN_STYLE_RE.search(value):
                return True
        return False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip or self._hides(tag, attrs):
            if tag not in _VOID_HTML_TAGS:
                self._skip.append(tag)
            return
        if tag in _BLOCK_HTML_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID_HTML_TAGS:
            return
        if self._skip:
            if tag == self._skip[-1]:
                self._skip.pop()
            return
        if tag in _BLOCK_HTML_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def _tick_run_length(markdown: str, index: int) -> int:
    run = 1
    while index + run < len(markdown) and markdown[index + run] == "`":
        run += 1
    return run


def _code_span_close(markdown: str, index: int, tick_len: int) -> int | None:
    scan = index + tick_len
    length = len(markdown)
    while scan < length:
        if markdown[scan] != "`":
            scan += 1
            continue
        run = _tick_run_length(markdown, scan)
        if run == tick_len:
            return scan
        scan += run
    return None


def _protect_inline_code_spans(markdown: str) -> str:
    """Keep inline-code angle brackets from being parsed as HTML tags."""
    result: list[str] = []
    index = 0
    length = len(markdown)
    while index < length:
        if markdown[index] != "`":
            result.append(markdown[index])
            index += 1
            continue
        tick_len = _tick_run_length(markdown, index)
        found = _code_span_close(markdown, index, tick_len)
        if found is None:
            result.append(markdown[index : index + tick_len])
            index += tick_len
            continue
        inner = markdown[index + tick_len : found]
        result.append(
            "`" * tick_len + inner.replace("<", " ").replace(">", " ") + "`" * tick_len
        )
        index = found + tick_len
    return "".join(result)


def _strip_non_rendered_html(markdown: str) -> str:
    parser = _VisibleHtmlText()
    parser.feed(_protect_inline_code_spans(markdown))
    parser.close()
    return "".join(parser.parts)
