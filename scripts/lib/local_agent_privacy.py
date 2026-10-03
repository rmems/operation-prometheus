"""Privacy and evidence checks for trainable Hermes exports."""

from __future__ import annotations

import re
from typing import Any

from .ci_private_refs import private_reference_errors
from .hermes_sanitize import strip_hidden_reasoning
from .secrets import find_secrets

HOME_PATH_RE = re.compile(
    r"("
    r"/home/[A-Za-z0-9._-]+"
    r"|/Users/[A-Za-z0-9._-]+"
    r"|/root(?:/[^\s\"']+)?"
    r"|(?:[A-Za-z]:\\Users\\|[A-Za-z]:/Users/)[A-Za-z0-9._-]+"
    r")",
    re.IGNORECASE,
)
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_PREFIXED_SHA256_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_CLOUD_FALLBACK_TEXT_RE = re.compile(
    r"cloud_fallback_allowed\W+true",
    re.IGNORECASE,
)
_SUCCESS_OUTCOMES = frozenset(
    {"pass", "passed", "success", "successful", "verified", "ok"}
)
_FAILED_OUTCOMES = frozenset({"fail", "failed", "error", "falsified"})


def hidden_reasoning_errors(value: Any) -> list[str]:
    if strip_hidden_reasoning(value) != value:
        return ["hidden reasoning is present"]
    return []


def cloud_fallback_errors(value: Any) -> list[str]:
    if isinstance(value, dict):
        errors = _nested_cloud_errors(value)
        if value.get("cloud_fallback_allowed") is True:
            errors.append("cloud fallback is allowed")
        return errors
    if isinstance(value, list):
        return [item for entry in value for item in cloud_fallback_errors(entry)]
    return []


def _nested_cloud_errors(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for nested in value.values():
        errors.extend(cloud_fallback_errors(nested))
    return errors


def hash_errors(value: Any) -> list[str]:
    return _hash_errors(value, "")


def _hash_errors(value: Any, key: str) -> list[str]:
    if isinstance(value, dict):
        return [
            item
            for child_key, child in value.items()
            for item in _hash_errors(child, str(child_key))
        ]
    if isinstance(value, list):
        return _hash_list_errors(value, key)
    return _hash_scalar_errors(value, key)


def _hash_list_errors(value: list[Any], key: str) -> list[str]:
    if not _is_hash_key(key):
        return [
            item for entry in value for item in _hash_errors(entry, key)
        ]
    if all(isinstance(item, str) and _SHA256_RE.fullmatch(item) for item in value):
        return []
    return [f"invalid hash {key}"]


def _hash_scalar_errors(value: Any, key: str) -> list[str]:
    if key == "ollama_digest":
        if isinstance(value, str) and _PREFIXED_SHA256_RE.fullmatch(value):
            return []
        return ["invalid ollama_digest"]
    if not _is_hash_key(key):
        return []
    if isinstance(value, str) and _SHA256_RE.fullmatch(value):
        return []
    return [f"invalid hash {key}"]


def _is_hash_key(key: str) -> bool:
    return key == "sha256" or key.endswith("_sha256")


def trainable_text_errors(text: str) -> list[str]:
    errors = list(private_reference_errors(text))
    if _has_home_path(text):
        errors.append("absolute user-home path present")
    if find_secrets(text):
        errors.append("secret-like token pattern present")
    if hidden_reasoning_errors(text):
        errors.append("hidden reasoning is present")
    if _CLOUD_FALLBACK_TEXT_RE.search(text):
        errors.append("cloud fallback is allowed")
    return errors


def _has_home_path(text: str) -> bool:
    return HOME_PATH_RE.search(text) is not None


def false_success_errors(record: dict[str, Any]) -> list[str]:
    if record.get("terminal_disposition") != "successful":
        return []
    outcome = _verifier_outcome(record)
    if outcome in _SUCCESS_OUTCOMES:
        return []
    if outcome in _FAILED_OUTCOMES:
        return ["failed verifier became a successful trajectory"]
    return ["successful terminal lacks independent verifier success"]


def _verifier_outcome(record: dict[str, Any]) -> str:
    provenance = record.get("execution_provenance")
    if not isinstance(provenance, dict):
        return ""
    verifier = provenance.get("verifier")
    if not isinstance(verifier, dict):
        return ""
    outcome = verifier.get("outcome")
    if not isinstance(outcome, str):
        return ""
    return outcome.strip().casefold()
