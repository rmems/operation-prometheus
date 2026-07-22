"""Secret scanning and redaction for trajectory artifacts."""

from __future__ import annotations

import re
from typing import Any

# High-confidence secret patterns. Prefer redaction over failing collection.
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("github_pat", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("github_fine_grained", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    # Full PEM when END present; truncated / unified-diff lines after BEGIN.
    (
        "private_key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
            r"(?:"
            r"[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
            r"|"
            # Base64 body, optional unified-diff +/- prefixes per line
            r"(?:[ \t]*[+-]?[A-Za-z0-9+/= \t]*\r?\n?){1,400}"
            r")"
        ),
    ),
    # OpenAI-style keys including sk-proj-..., sk-svcacct-..., etc.
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("slack_webhook", re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/_-]+")),
    # Quoted values (may contain spaces) OR unquoted tokens.
    ("generic_api_assignment", re.compile(
        r"(?i)\b(api[_-]?key|secret|password|token)\s*[=:]\s*"
        r"(?:"
        r"['\"][^'\"]{12,}['\"]"
        r"|"
        r"[^'\"\s]{12,}"
        r")"
    )),
]

# Local absolute user-home paths (Linux, macOS, Windows) — must not enter training data.
_HOME_PATH = re.compile(
    r"(?i)"
    r"(?:"
    r"/home/[A-Za-z0-9._-]+(?:/[^\s\"']+)?"
    r"|/Users/[A-Za-z0-9._-]+(?:/[^\s\"']+)?"
    r"|(?:[A-Za-z]:\\Users\\|[A-Za-z]:/Users/)[A-Za-z0-9._-]+(?:[\\/][^\s\"']+)?"
    r")",
    re.IGNORECASE,
)


def find_secrets(text: str) -> list[str]:
    """Return names of secret pattern families that matched."""
    hits: list[str] = []
    for name, pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            hits.append(name)
    return hits


def redact_secrets(text: str) -> tuple[str, int]:
    """Redact secret-like substrings. Returns (text, redaction_count)."""
    count = 0
    out = text
    for _name, pattern in _SECRET_PATTERNS:
        out, n = pattern.subn("[REDACTED]", out)
        count += n
    return out, count


def redact_home_paths(text: str) -> tuple[str, int]:
    """Replace absolute user-home paths (/home, /Users, C:\\Users) with a placeholder."""
    out, n = _HOME_PATH.subn("[HOME_PATH]", text)
    return out, n


def sanitize_text(text: str) -> tuple[str, list[str]]:
    """Redact secrets and home paths. Returns (text, warning strings)."""
    warnings: list[str] = []
    out, n_sec = redact_secrets(text)
    if n_sec:
        warnings.append(f"redacted_{n_sec}_secret_matches")
    out, n_home = redact_home_paths(out)
    if n_home:
        warnings.append(f"redacted_{n_home}_home_paths")
    return out, warnings


def scan_and_sanitize_obj(obj: Any) -> tuple[Any, list[str]]:
    """Recursively sanitize strings in a JSON-serializable structure."""
    warnings: list[str] = []

    def walk(value: Any) -> Any:
        if isinstance(value, str):
            cleaned, w = sanitize_text(value)
            warnings.extend(w)
            return cleaned
        if isinstance(value, list):
            return [walk(v) for v in value]
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        return value

    return walk(obj), warnings
