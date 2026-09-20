"""Markdown link and reference stripping for license-section disclosure."""

from __future__ import annotations

from .license_closure_pr_html import (
    MARKDOWN_REFERENCE_DESTINATION_RE,
    MARKDOWN_REFERENCE_TITLE_RE,
    _tick_run_length,
)


def _label_colon_index(line: str, index: int) -> int | None:
    if line[index : index + 1] != "[":
        return None
    close = _markdown_label_close(line, index + 1)
    if close is None or line[close + 1 : close + 2] != ":":
        return None
    return close


def _reference_definition_kind(line: str) -> str | None:
    index = len(line) - len(line.lstrip(" \t"))
    close = _label_colon_index(line, index)
    if close is None:
        return None
    return "full" if line[close + 2 :].strip() else "label_only"


def _title_line_end(lines: list[str], index: int) -> int:
    if index < len(lines) and MARKDOWN_REFERENCE_TITLE_RE.match(lines[index]):
        return index + 1
    return index


def _reference_definition_span(lines: list[str], index: int) -> int | None:
    kind = _reference_definition_kind(lines[index])
    if kind == "full":
        return _title_line_end(lines, index + 1)
    if kind != "label_only":
        return None
    nxt = index + 1
    if nxt < len(lines) and MARKDOWN_REFERENCE_DESTINATION_RE.match(lines[nxt]):
        return _title_line_end(lines, nxt + 1)
    return None


def _strip_reference_definitions(markdown: str) -> str:
    lines = markdown.split("\n")
    kept: list[str] = []
    index = 0
    while index < len(lines):
        skipped = _reference_definition_span(lines, index)
        if skipped is not None:
            index = skipped
            continue
        kept.append(lines[index])
        index += 1
    return "\n".join(kept)


def _escaped_span_end(markdown: str, index: int, closer: str) -> int | None:
    while index < len(markdown):
        char = markdown[index]
        if char == "\\":
            index += 2
            continue
        if char == "\n":
            return None
        if char == closer:
            return index + 1
        index += 1
    return None


def _title_closer(opener: str) -> str:
    return ")" if opener == "(" else opener


def _skip_markdown_link_title(markdown: str, index: int) -> int | None:
    if index >= len(markdown):
        return index
    opener = markdown[index]
    if opener not in "\"'(":
        return index
    return _escaped_span_end(markdown, index + 1, _title_closer(opener))


def _skip_spaces(markdown: str, index: int) -> int:
    length = len(markdown)
    while index < length and markdown[index] in " \t":
        index += 1
    return index


def _angle_destination_end(markdown: str, index: int) -> int | None:
    return _escaped_span_end(markdown, index + 1, ">")


def _escaped_positions(markdown: str) -> frozenset[int]:
    positions: set[int] = set()
    cursor = markdown.find("\\")
    while -1 < cursor < len(markdown) - 1:
        positions.add(cursor + 1)
        cursor = markdown.find("\\", cursor + 2)
    return frozenset(positions)


def _bare_destination_end(markdown: str, index: int) -> int | None:
    escaped = _escaped_positions(markdown)
    depth = 0
    for cursor in range(index, len(markdown)):
        if cursor in escaped:
            continue
        char = markdown[cursor]
        if char == "\n":
            return None
        depth += (char == "(") - (char == ")")
        if depth < 0:
            return cursor
        if char in " \t" and depth == 0:
            return cursor
    return None


def _link_destination_end(markdown: str, index: int) -> int | None:
    if markdown[index] == "<":
        return _angle_destination_end(markdown, index)
    return _bare_destination_end(markdown, index)


def _inline_link_close(markdown: str, start: int) -> int | None:
    length = len(markdown)
    index = _skip_spaces(markdown, start)
    if index >= length:
        return None
    end = _link_destination_end(markdown, index)
    if end is None:
        return None
    index = _skip_spaces(markdown, end)
    titled = _skip_markdown_link_title(markdown, index)
    if titled is None:
        return None
    index = _skip_spaces(markdown, titled)
    if index < length and markdown[index] == ")":
        return index
    return None


def _code_span_end(markdown: str, index: int, tick_len: int) -> int | None:
    scan = index + tick_len
    length = len(markdown)
    while scan < length:
        char = markdown[scan]
        if char == "\n":
            return None
        if char != "`":
            scan += 1
            continue
        run = _tick_run_length(markdown, scan)
        if run == tick_len:
            return scan + run
        scan += run
    return None


def _code_span_skip(markdown: str, index: int) -> int:
    end = _code_span_end(markdown, index, _tick_run_length(markdown, index))
    return end if end is not None else index + 1


def _markdown_label_close(markdown: str, text_start: int) -> int | None:
    depth = 1
    index = text_start
    length = len(markdown)
    while index < length:
        char = markdown[index]
        if char == "\\":
            index += 2
            continue
        if char == "\n":
            return None
        if char == "`":
            index = _code_span_skip(markdown, index)
            continue
        depth += (char == "[") - (char == "]")
        if depth == 0:
            return index
        index += 1
    return None


def _link_opener_len(markdown: str, index: int) -> int:
    if markdown[index] == "[":
        return 1
    is_image = markdown[index] == "!" and markdown[index + 1 : index + 2] == "["
    return 2 if is_image else 0


def _inline_link_span(
    markdown: str, index: int
) -> tuple[int, int, int] | None:
    opener = _link_opener_len(markdown, index)
    if not opener:
        return None
    text_start = index + opener
    close = _markdown_label_close(markdown, text_start)
    if close is None or markdown[close + 1 : close + 2] != "(":
        return None
    dest_close = _inline_link_close(markdown, close + 2)
    if dest_close is None:
        return None
    return text_start, close, dest_close


def _strip_inline_links(markdown: str, *, keep_openers: bool = False) -> str:
    result: list[str] = []
    index = 0
    length = len(markdown)
    while index < length:
        span = _inline_link_span(markdown, index)
        if span is None:
            result.append(markdown[index])
            index += 1
            continue
        index = _emit_link_text(result, markdown, span, keep_openers)
    return "".join(result)


def _emit_link_text(
    result: list[str], markdown: str, span: tuple[int, int, int], keep_openers: bool
) -> int:
    text_start, close, dest_close = span
    if keep_openers:
        result.append("[")
    result.append(
        _strip_inline_links(markdown[text_start:close], keep_openers=keep_openers)
    )
    return dest_close + 1
