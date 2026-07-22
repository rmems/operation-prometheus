"""Unit tests for bot filtering and secret redaction."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.bots import is_bot_user, strip_bot_boilerplate  # noqa: E402
from lib.secrets import redact_home_paths, redact_secrets, sanitize_text  # noqa: E402


def test_is_bot_user_by_type_and_login():
    assert is_bot_user("rmems", "User") is False
    assert is_bot_user("codecov[bot]", "Bot") is True
    assert is_bot_user("codeant-ai", "User") is True
    assert is_bot_user("dependabot", None) is True


def test_strip_codeant_boilerplate():
    body = (
        "## Summary\nReal content here.\n\n"
        "## **CodeAnt-AI Description**\n### Checking Your Pull Request\nspam"
    )
    cleaned = strip_bot_boilerplate(body)
    assert "Real content" in cleaned
    assert "CodeAnt" not in cleaned


def test_redact_github_token_and_home_path():
    text = "token=ghp_ABCDEFGHIJKLMNOPQRSTUVWX and path=/home/raulmc/.models/foo"
    out, n = redact_secrets(text)
    assert n >= 1
    assert "ghp_" not in out
    out2, n2 = redact_home_paths(out)
    assert n2 >= 1
    assert "/home/raulmc" not in out2
    cleaned, warnings = sanitize_text(text)
    assert "[REDACTED]" in cleaned
    assert "[HOME_PATH]" in cleaned
    assert warnings
