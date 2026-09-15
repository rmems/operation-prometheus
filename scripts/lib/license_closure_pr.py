"""Pull-request provenance and markdown disclosure for source-license closure."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

from .license_closure_ids import (
    GIT_OID_RE,
    MARKDOWN_LICENSE_SECTION_RE,
    MARKDOWN_SECTION_BOUNDARY_RE,
    _sha256_or_none,
    _text,
)
from .source_inventory_common import sha256_json

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
MARKDOWN_REFERENCE_DEFINITION_RE = re.compile(r"^\s*\[[^\]\n]+\]:\s+\S")
MARKDOWN_REFERENCE_LABEL_ONLY_RE = re.compile(r"^\s*\[[^\]\n]+\]:\s*$")
MARKDOWN_REFERENCE_DESTINATION_RE = re.compile(r"""^[ \t]*(?:<[^>\n]*>|\S+)\s*$""")
MARKDOWN_REFERENCE_TITLE_RE = re.compile(
    r"""^[ \t]+(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\((?:\\.|[^)\\])*\))\s*$"""
)
MARKDOWN_REFERENCE_LINK_RE = re.compile(r"!?\[([^\]\n]*)\]\[[^\]\n]*\]")
FENCE_OPEN_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})")


def pr_inventory_row_source_hash(row: dict[str, Any]) -> str:
    """Hash the supplied PR inventory row, excluding ``source_hash``.

    Eligibility producer hashes bind unsanitized GraphQL title/body, which
    published PR rows do not keep. Authenticate the published object used
    for code-state matching instead so a stale digest cannot cover edited
    base/head/merge OIDs.
    """
    payload = {key: value for key, value in row.items() if key != "source_hash"}
    return sha256_json(payload)


def _valid_oid(value: Any) -> str | None:
    text = _text(value)
    if GIT_OID_RE.fullmatch(text):
        return text.lower()
    return None


_RECORD_TO_PR_ROLE = (
    ("base_oid", "base_oid"),
    ("head_oid", "head_oid"),
    ("commit_oid", "merge_commit_oid"),
    ("merge_commit_oid", "merge_commit_oid"),
)


def _record_role_oids(record: dict[str, Any], key: str) -> set[str]:
    container = record.get("repository")
    if not isinstance(container, dict):
        return set()
    oid = _valid_oid(container.get(key))
    return {oid} if oid is not None else set()


def _present_role_oid_invalid(record: dict[str, Any], key: str) -> bool:
    container = record.get("repository")
    if not isinstance(container, dict) or key not in container:
        return False
    return _valid_oid(container[key]) is None


def _code_state_matches_inventory_pr(
    record: dict[str, Any],
    inventory_pr: dict[str, Any],
) -> bool:
    pr_oids = {
        "base_oid": _valid_oid(inventory_pr.get("base_oid")),
        "head_oid": _valid_oid(inventory_pr.get("head_oid")),
        "merge_commit_oid": _valid_oid(inventory_pr.get("merge_commit_oid")),
    }
    if not any(pr_oids.values()):
        return False
    saw_record_oid = False
    saw_merge = False
    for record_key, pr_key in _RECORD_TO_PR_ROLE:
        if _present_role_oid_invalid(record, record_key):
            return False
        record_oids = _record_role_oids(record, record_key)
        if not record_oids:
            continue
        saw_record_oid = True
        if pr_key == "merge_commit_oid":
            saw_merge = True
        expected = pr_oids[pr_key]
        if expected is None or any(oid != expected for oid in record_oids):
            return False
    return saw_record_oid and saw_merge


def _pr_inventory_reasons(
    record: dict[str, Any],
    repos: list[str],
    pr_number: int | None,
    pull_requests: dict[tuple[str, int], dict[str, Any]] | None,
    repository: dict[str, Any] | None = None,
) -> list[str]:
    if pull_requests is None:
        return []
    names = [name for name in repos if name]
    if not names or pr_number is None:
        return ["snapshot_provenance_missing"]
    inventory_id = _text((repository or {}).get("repository_id"))
    seen: set[str] = set()
    matched: list[dict[str, Any]] = []
    seen_evidence: set[str] = set()
    for name in names:
        folded = name.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        inventory_pr = pull_requests.get((folded, pr_number))
        if inventory_pr is None:
            continue
        pr_id = _text(inventory_pr.get("repository_id"))
        if inventory_id and pr_id and inventory_id != pr_id:
            return ["snapshot_provenance_missing"]
        evidence = sha256_json(
            {
                "base_oid": inventory_pr.get("base_oid"),
                "head_oid": inventory_pr.get("head_oid"),
                "merge_commit_oid": inventory_pr.get("merge_commit_oid"),
                "number": inventory_pr.get("number"),
            }
        )
        if evidence in seen_evidence:
            continue
        seen_evidence.add(evidence)
        matched.append(inventory_pr)
    if len(matched) > 1:
        raise ValueError(f"Duplicate inventory pull request {names[0]}#{pr_number}")
    if matched and _code_state_matches_inventory_pr(record, matched[0]):
        return []
    return ["snapshot_provenance_missing"]


def _index_pull_requests(
    pull_requests: list[dict[str, Any]] | None,
) -> dict[tuple[str, int], dict[str, Any]]:
    index: dict[tuple[str, int], dict[str, Any]] = {}
    for row in pull_requests or []:
        if not isinstance(row, dict):
            raise ValueError("pull-request inventory rows must be objects")
        repo = _text(row.get("repository_name_with_owner")).casefold()
        number = row.get("number")
        if not repo or type(number) is not int or number < 1:
            raise ValueError(
                "pull-request inventory row is missing a repository name or PR number"
            )
        declared = _sha256_or_none(row.get("source_hash"))
        if declared is None or declared != pr_inventory_row_source_hash(row):
            raise ValueError(
                "pull-request inventory source_hash does not match the published row"
            )
        key = (repo, number)
        if key in index:
            raise ValueError(f"Duplicate inventory pull request {repo}#{number}")
        index[key] = row
    return index


def _declared_repos(container: dict[str, Any]) -> set[str]:
    names = [_text(container.get("source_repo"))]
    extra = container.get("source_repos")
    if isinstance(extra, list):
        names.extend(_text(item) for item in extra if isinstance(item, str))
    return {name.casefold() for name in names if name}


def _source_coverage_invalid(container: dict[str, Any]) -> bool:
    if "source_repo" in container:
        singular = container.get("source_repo")
        if not isinstance(singular, str) or not singular.strip():
            return True
    if "source_repos" in container:
        extra = container.get("source_repos")
        if not isinstance(extra, list):
            return True
        if any(not isinstance(item, str) or not item.strip() for item in extra):
            return True
    return not _declared_repos(container)


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
        if self._skip:
            if tag not in _VOID_HTML_TAGS:
                self._skip.append(tag)
            return
        if self._hides(tag, attrs):
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


def _strip_non_rendered_html(markdown: str) -> str:
    parser = _VisibleHtmlText()
    parser.feed(markdown)
    parser.close()
    return "".join(parser.parts)


def _strip_reference_definitions(markdown: str) -> str:
    lines = markdown.split("\n")
    kept: list[str] = []
    index = 0
    while index < len(lines):
        if MARKDOWN_REFERENCE_DEFINITION_RE.match(lines[index]):
            index += 1
            if index < len(lines) and MARKDOWN_REFERENCE_TITLE_RE.match(lines[index]):
                index += 1
            continue
        if MARKDOWN_REFERENCE_LABEL_ONLY_RE.match(lines[index]):
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
        gt = markdown.find(">", index + 1)
        if gt == -1 or "\n" in markdown[index:gt]:
            return None
        index = gt + 1
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
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _strip_inline_links(markdown: str) -> str:
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
                    result.append(markdown[text_start:close])
                    index = dest_close + 1
                    continue
        result.append(markdown[index])
        index += 1
    return "".join(result)


def _visible_markdown_text(markdown: str) -> str:
    visible = HTML_COMMENT_RE.sub("", markdown)
    visible = _strip_reference_definitions(visible)
    visible = _strip_inline_links(visible)
    visible = MARKDOWN_REFERENCE_LINK_RE.sub(r"\1", visible)
    visible = _strip_non_rendered_html(visible)
    return HTML_TAG_RE.sub("", visible)


def _strip_hidden_markup(markdown: str) -> str:
    return _strip_non_rendered_html(HTML_COMMENT_RE.sub("", markdown))


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
