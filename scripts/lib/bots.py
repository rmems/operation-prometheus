"""Bot detection and PR body boilerplate stripping."""

from __future__ import annotations

import re

# Login substrings / exact-ish names that are automation, not engineering review.
BOT_LOGIN_MARKERS: tuple[str, ...] = (
    "[bot]",
    "dependabot",
    "renovate",
    "github-actions",
    "codecov",
    "codeant",
    "macroscope",
    "copilot",
    "cursor",
    "sentry",
    "linear-app",
    "imgbot",
    "greptile",
    "coderabbit",
    "devin-ai",
    "kilo-code",
    "gitar",
    "bugbot",
)

# Automated reviewers that still leave actionable engineering comments.
# These are kept for review_signals even when type=Bot / login ends with [bot].
ENGINEERING_REVIEW_ALLOWLIST: tuple[str, ...] = (
    "gemini-code-assist",
    "chatgpt-codex-connector",
    "chatgpt-codex",
    "codex",
)

# Known product footers that pollute issue_context when left in PR bodies.
_BOILERPLATE_MARKERS = (
    "## **CodeAnt-AI Description**",
    "### Checking Your Pull Request",
    "💡 Usage Guide",
    "<!-- CURSOR_SUMMARY -->",
    "<!-- /CURSOR_SUMMARY -->",
    "<!-- devin-review-badge-begin -->",
    "Reviewed by [Cursor Bugbot]",
    "Open in Devin Review",
)

# Strip full marker-delimited bot blocks (content between markers), not only tags.
_CURSOR_BLOCK = re.compile(
    r"<!--\s*CURSOR_SUMMARY\s*-->.*?<!--\s*/CURSOR_SUMMARY\s*-->",
    re.DOTALL | re.IGNORECASE,
)
_DEVIN_BLOCK = re.compile(
    r"<!--\s*devin-review-badge-begin\s*-->.*?<!--\s*devin-review-badge-end\s*-->",
    re.DOTALL | re.IGNORECASE,
)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_CODEANT_BLOCK = re.compile(
    r"##\s*\*\*CodeAnt-AI Description\*\*.*",
    re.DOTALL | re.IGNORECASE,
)
_MACROSCOPE_NOTE = re.compile(
    r">\s*\[!NOTE\].*?Macroscope summarized.*?(?:\n\n|\Z)",
    re.DOTALL | re.IGNORECASE,
)
# Gemini Code Assist IMPORTANT lifecycle admonitions (full blockquote runs).
# Last line may omit trailing newline at EOF.
_GEMINI_IMPORTANT_BLOCK = re.compile(
    r"(?is)(?:^|\n)\s*>\s*\[!IMPORTANT\]\s*\n(?:\s*>[^\n]*(?:\n|$))+",
)


def is_bot_user(login: str | None, user_type: str | None = None) -> bool:
    """Return True if the author should be excluded from review_signals."""
    if not login:
        return bool(user_type and user_type.lower() == "bot")
    low = login.lower().replace("[bot]", "")
    if any(allowed in low for allowed in ENGINEERING_REVIEW_ALLOWLIST):
        return False
    if user_type and user_type.lower() == "bot":
        return True
    if login.lower().endswith("[bot]"):
        return True
    return any(marker in login.lower() for marker in BOT_LOGIN_MARKERS)


def strip_bot_boilerplate(markdown: str) -> str:
    """Remove common automated PR description footers."""
    if not markdown:
        return ""
    # Remove full bot blocks first (so inner content does not leak).
    text = _CURSOR_BLOCK.sub("", markdown)
    text = _DEVIN_BLOCK.sub("", text)
    text = _HTML_COMMENT.sub("", text)
    text = _CODEANT_BLOCK.sub("", text)
    text = _MACROSCOPE_NOTE.sub("", text)
    # Drop Gemini IMPORTANT lifecycle/sunset blockquotes only (keep other notes).
    def _drop_gemini_lifecycle(m: re.Match[str]) -> str:
        block = m.group(0).lower()
        if "sunset" in block or "deprecat" in block or "gemini code assist" in block:
            return "\n"
        return m.group(0)

    text = _GEMINI_IMPORTANT_BLOCK.sub(_drop_gemini_lifecycle, text)

    # Cut at first strong boilerplate marker if remaining.
    cut_at = len(text)
    for marker in _BOILERPLATE_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            cut_at = min(cut_at, idx)
    text = text[:cut_at]

    # Collapse excessive blank lines.
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _heading_level(line: str) -> int:
    """Return the markdown heading level of a line, or 0 if it is not a heading."""
    n = len(line) - len(line.lstrip("#"))
    return n if line[n : n + 1] == " " else 0


def _heading_matches_keyword(line: str, keyword: str) -> bool:
    """True when heading title equals/starts with keyword (not parenthetical mentions).

    Avoids matching ``#### Commands run (summary)`` for keyword ``summary``.
    """
    level = _heading_level(line)
    if not level:
        return False
    title = line[level:].strip().lower()
    # Drop trailing punctuation / emoji noise for matching.
    title = re.sub(r"[^\w\s:-]+", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    kw = keyword.lower().strip()
    return title == kw or title.startswith(kw + " ") or title.startswith(kw + ":")


def extract_section(markdown: str, heading_keywords: tuple[str, ...]) -> str | None:
    """Extract a markdown section whose heading title matches any keyword."""
    if not markdown:
        return None
    lines = markdown.splitlines()
    start: int | None = None
    start_level = 0
    for i, line in enumerate(lines):
        if not line.startswith("#"):
            continue
        if any(_heading_matches_keyword(line, k) for k in heading_keywords):
            start = i + 1
            start_level = _heading_level(line)
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start, len(lines)):
        lvl = _heading_level(lines[j])
        # stop only at a heading of equal or higher level (fewer/equal '#')
        if lvl and lvl <= start_level:
            end = j
            break
    body = "\n".join(lines[start:end]).strip()
    return body or None
