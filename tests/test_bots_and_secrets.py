"""Unit tests for bot filtering and secret redaction."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.bots import extract_section, is_bot_user, strip_bot_boilerplate  # noqa: E402
from lib.secrets import find_secrets, redact_home_paths, redact_secrets, sanitize_text  # noqa: E402


def test_extract_section_ignores_parenthetical_summary():
    body = (
        "### What changed\n\nReplaces the PRNG.\n\n"
        "#### Commands run (summary)\n\n| Command | Pass means |\n"
    )
    assert "Replaces" in (extract_section(body, ("what changed",)) or "")
    assert extract_section(body, ("summary",)) is None


def test_extract_section_matches_prefixed_validation_headings():
    body = (
        "## Local testing\n\n`cargo test` green.\n\n"
        "## Manual verification\n\nSanitizer clean.\n\n"
        "## Other\n\nnoise\n"
    )
    assert "cargo test" in (extract_section(body, ("testing", "tests")) or "")
    assert "Sanitizer" in (extract_section(body, ("verification",)) or "")


def test_strip_gemini_sunset_boilerplate():
    body = (
        "## Code Review\n\nFix the panic path.\n\n"
        "> [!IMPORTANT]\n"
        "> The consumer version of Gemini Code Assist on GitHub is being sunset.\n"
        "> For more details on the timeline, see Help Documentation.\n"
    )
    cleaned = strip_bot_boilerplate(body)
    assert "Fix the panic path" in cleaned
    assert "sunset" not in cleaned.lower()
    assert "Help Documentation" not in cleaned


def test_keep_actionable_deprecation_important_blocks():
    body = (
        "## Code Review\n\nPlease migrate callers.\n\n"
        "> [!IMPORTANT]\n"
        "> `OldApi` is deprecated; use `NewApi` instead to avoid breakage.\n"
    )
    cleaned = strip_bot_boilerplate(body)
    assert "deprecated" in cleaned.lower()
    assert "NewApi" in cleaned


def test_keep_non_gemini_sunset_important_blocks():
    body = (
        "## Code Review\n\nPlan the migration.\n\n"
        "> [!IMPORTANT]\n"
        "> We will sunset the old endpoint next quarter; migrate clients now.\n"
    )
    cleaned = strip_bot_boilerplate(body)
    assert "sunset the old endpoint" in cleaned


def test_strip_codex_react_footer():
    body = (
        "Avoid forcing the JS entropy backend from the library.\n\n"
        "Useful? React with 👍 / 👎."
    )
    cleaned = strip_bot_boilerplate(body)
    assert "JS entropy" in cleaned
    assert "Useful?" not in cleaned
    assert "React with" not in cleaned


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


def test_redact_macos_windows_paths_and_sk_proj():
    # Synthetic fixture only — not a real credential.
    fake_key = "sk-proj-" + ("x" * 24)
    text = (
        f"key={fake_key} "
        f'mac=/Users/alice/.ssh/id_rsa '
        f'win=C:\\Users\\Alice\\.env '
        f'root=/root/.ssh/id_rsa '
        f'password="correct horse battery staple"'
    )
    cleaned, warnings = sanitize_text(text)
    assert fake_key not in cleaned
    assert "/Users/alice" not in cleaned
    assert "Users\\Alice" not in cleaned and "Users/Alice" not in cleaned
    assert "/root/" not in cleaned
    assert "correct horse" not in cleaned
    assert "[REDACTED]" in cleaned
    assert "[HOME_PATH]" in cleaned
    assert warnings


def test_redact_diff_prefixed_truncated_pem():
    # Synthetic PEM-like body for redaction coverage only.
    text = (
        "- -----BEGIN PRIVATE KEY-----\n"
        "-" + ("A" * 40) + "\n"
        "-" + ("B" * 40) + "\n"
    )
    cleaned, _ = sanitize_text(text)
    assert "A" * 20 not in cleaned
    assert "[REDACTED]" in cleaned


def test_find_secrets_covers_slack_and_password_assignment():
    slack = "https://hooks.slack.com/services/T000/B000/XXXXXXXXXXXXXXXXXXXXXXXX"
    password = "password=abcdefghijklmnop"
    assert "slack_webhook" in find_secrets(slack)
    assert "generic_api_assignment" in find_secrets(password)
    assert find_secrets("harmless text without credentials") == []


def test_generic_secret_does_not_redact_code_expressions():
    code = 'let api_key = std::env::var("NR_INSERT_KEY").ok();'
    cleaned, n = redact_secrets(code)
    assert n == 0
    assert "std::env::var" in cleaned
    assert "api_key" in cleaned
    # Real-looking env-file literal still redacted (synthetic, not a live key).
    lit = "api_key=" + ("x" * 24)
    cleaned2, n2 = redact_secrets(lit)
    assert n2 >= 1
    assert ("x" * 24) not in cleaned2
