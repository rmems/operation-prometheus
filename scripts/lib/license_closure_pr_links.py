"""Markdown link and reference stripping for license-section disclosure."""

from __future__ import annotations

from .license_closure_pr_html import (
    MARKDOWN_REFERENCE_DESTINATION_RE,
    MARKDOWN_REFERENCE_TITLE_RE,
)

def _reference_definition_kind(line: str) -> str | None:
    index = 0
    while index < len(line) and line[index] in " \t":
        index += 1
    if index >= len(line) or line[index] != "[":
        return None
    close = _markdown_label_close(line, index + 1)
    if close is None or close + 1 >= len(line) or line[close + 1] != ":":
        return None
    rest = line[close + 2 :]
    if not rest.strip():
        return "label_only"
    return "full"


def _strip_reference_definitions(markdown: str) -> str:
    lines = markdown.split("\n")
    kept: list[str] = []
    index = 0
    while index < len(lines):
        kind = _reference_definition_kind(lines[index])
        if kind == "full":
            index += 1
            if index < len(lines) and MARKDOWN_REFERENCE_TITLE_RE.match(lines[index]):
                index += 1
            continue
        if kind == "label_only":
            nxt = index + 1
            if nxt < len(lines) and MARKDOWN_REFERENCE_DESTINATION_RE.match(lines[nxt]):
                index = nxt + 1
                if index < len(lines) and MARKDOWN_REFERENCE_TITLE_RE.match(
                    lines[index]
                ):
                    index += 1
                continue
        kept.append(lines[index])
        index += 1
    return "\n".join(kept)


def _skip_markdown_link_title(markdown: str, index: int) -> int | None:
    if index >= len(markdown):
        return index
    opener = markdown[index]
    if opener not in "\"'(":
        return index
    closer = ")" if opener == "(" else opener
    index += 1
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


def _inline_link_close(markdown: str, start: int) -> int | None:
    index = start
    length = len(markdown)
    while index < length and markdown[index] in " \t":
        index += 1
    if index >= length:
        return None
    if markdown[index] == "<":
        scan = index + 1
        while scan < length:
            char = markdown[scan]
            if char == "\\":
                scan += 2
                continue
            if char == "\n":
                return None
            if char == ">":
                index = scan + 1
                break
            scan += 1
        else:
            return None
    else:
        depth = 0
        while index < length:
            char = markdown[index]
            if char == "\\":
                index += 2
                continue
            if char == "\n":
                return None
            if char in " \t" and depth == 0:
                break
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    return index
                depth -= 1
            index += 1
        else:
            return None
    while index < length and markdown[index] in " \t":
        index += 1
    titled = _skip_markdown_link_title(markdown, index)
    if titled is None:
        return None
    index = titled
    while index < length and markdown[index] in " \t":
        index += 1
    if index < length and markdown[index] == ")":
        return index
    return None


def _skip_inline_code_span(markdown: str, index: int) -> int | None:
    length = len(markdown)
    tick_len = 1
    while index + tick_len < length and markdown[index + tick_len] == "`":
        tick_len += 1
    scan = index + tick_len
    while scan < length:
        char = markdown[scan]
        if char == "\n":
            return None
        if char != "`":
            scan += 1
            continue
        run = 1
        while scan + run < length and markdown[scan + run] == "`":
            run += 1
        if run == tick_len:
            return scan + run
        scan += run
    return None


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
            skipped = _skip_inline_code_span(markdown, index)
            if skipped is None:
                index += 1
                continue
            index = skipped
            continue
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _strip_inline_links(markdown: str, *, keep_openers: bool = False) -> str:
    result: list[str] = []
    index = 0
    length = len(markdown)
    while index < length:
        image = (
            markdown[index] == "!" and index + 1 < length and markdown[index + 1] == "["
        )
        if markdown[index] == "[" or image:
            text_start = index + (2 if image else 1)
            close = _markdown_label_close(markdown, text_start)
            if close is not None and close + 1 < length and markdown[close + 1] == "(":
                dest_close = _inline_link_close(markdown, close + 2)
                if dest_close is not None:
                    if keep_openers:
                        result.append("[")
                    result.append(
                        _strip_inline_links(
                            markdown[text_start:close], keep_openers=keep_openers
                        )
                    )
                    index = dest_close + 1
                    continue
        result.append(markdown[index])
        index += 1
    return "".join(result)
