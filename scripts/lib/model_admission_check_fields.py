"""Field-level checks for local-model admission candidates."""

from __future__ import annotations

from typing import Any

import re

from .model_admission_evidence import (
    _ENDPOINT_KEYS,
    _credential_string,
    _SECRET_KEY_RE,
    _SECRET_VALUE_RE,
    _nonempty_secret_value,
    canonical_loopback_endpoint,
    credential_config_values,
    endpoint_host,
    invalid_config_values,
    remote_config_endpoints,
    unknown_config_keys,
    unsanitized_config_keys,
)

SUPPORTED_RUNTIME = "ollama"

MODEL_IDENTITY_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*:[A-Za-z0-9][A-Za-z0-9._-]*$"
)
ALLOWED_CANDIDATE_KEYS = frozenset(
    {
        "model",
        "ollama_digest",
        "quantization",
        "upstream_revision",
        "runtime",
        "endpoint",
        "license",
        "provider_config",
        "probed_at",
    }
)
_FOREIGN_PROVIDER_HINTS = frozenset(
    {"provider", "vendor", "service", "api", "api_version"}
)


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def model_identity_reasons(candidate: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Strict ``name:tag`` grammar for the declared model identity."""
    model = candidate.get("model")
    if not isinstance(model, str) or not model.strip():
        return ["model_missing"], []
    if ":" not in model:
        return [], ["model_tag_missing"]
    if not MODEL_IDENTITY_RE.fullmatch(model.strip()):
        return ["model_invalid"], []
    return [], []


def _unknown_candidate_keys(candidate: dict[str, Any]) -> list[Any]:
    return [key for key in candidate if key not in ALLOWED_CANDIDATE_KEYS]


def _foreign_provider_key(key: Any) -> bool:
    return key.strip().lower() in _FOREIGN_PROVIDER_HINTS


def _unknown_key_flags(key: Any, value: Any) -> list[str]:
    flags: list[str] = []
    secret = _looks_secret(key, value)
    remote = _looks_remote_endpoint(key, value)
    if secret or remote:
        flags.append("candidate_unsanitized")
    if _foreign_provider_key(key):
        flags.append("foreign_provider_declared")
    return flags


def envelope_reasons(candidate: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Closed candidate envelope: unknown keys and foreign/secret values reject."""
    unknown = _unknown_candidate_keys(candidate)
    if not unknown:
        return [], []
    rejected = ["candidate_unknown_fields"]
    for key in unknown:
        rejected.extend(_unknown_key_flags(key, candidate.get(key)))
    return sorted(set(rejected)), []


def _key_names_secret(key: Any) -> bool:
    return isinstance(key, str) and bool(_SECRET_KEY_RE.search(key))


def _string_matches_secret(item: Any) -> bool:
    return isinstance(item, str) and bool(_SECRET_VALUE_RE.search(item))


def _secret_shaped_value(value: Any) -> bool:
    values = value if isinstance(value, list) else [value]
    return any(_string_matches_secret(item) for item in values)


def _looks_secret(key: Any, value: Any) -> bool:
    if _key_names_secret(key):
        return _nonempty_secret_value(value)
    return _secret_shaped_value(value)


def _endpoint_key(key: Any) -> bool:
    return isinstance(key, str) and key.strip().lower() in _ENDPOINT_KEYS


def _blank_endpoint(value: Any) -> bool:
    return not isinstance(value, str) or not value.strip()


def _looks_remote_endpoint(key: Any, value: Any) -> bool:
    if not _endpoint_key(key) or _blank_endpoint(value):
        return False
    return canonical_loopback_endpoint(value) is None


def _is_unsafe(value: Any) -> bool:
    return isinstance(value, str) and _credential_string(value)


def unsanitized_field_reasons(
    candidate: dict[str, Any], rights_row: Any
) -> list[str]:
    """Emitted untrusted strings must not carry secrets/unsafe references."""
    values = [candidate.get("quantization"), candidate.get("upstream_revision")]
    if isinstance(rights_row, dict):
        values.append(rights_row.get("terms_source"))
    return ["unsanitized_evidence"] if any(_is_unsafe(v) for v in values) else []


def runtime_reasons(candidate: dict[str, Any]) -> tuple[list[str], list[str]]:
    runtime = _text(candidate.get("runtime"))
    if runtime is None:
        return [], ["runtime_missing"]
    if runtime != SUPPORTED_RUNTIME:
        return ["runtime_unsupported"], []
    return [], []


def _host_is_loopback(host: str | None) -> bool:
    return host in ("localhost", "127.0.0.1", "::1")


def endpoint_reasons(candidate: dict[str, Any]) -> tuple[list[str], list[str]]:
    endpoint = candidate.get("endpoint")
    if _text(endpoint) is None:
        return [], ["endpoint_missing"]
    host = endpoint_host(endpoint)
    if host is not None and not _host_is_loopback(host):
        return ["endpoint_not_loopback"], []
    if canonical_loopback_endpoint(endpoint) is None:
        return [], ["endpoint_invalid"]
    return [], []


def _config_unsanitized(config: dict[str, Any]) -> bool:
    if unsanitized_config_keys(config):
        return True
    return bool(credential_config_values(config))


def _config_rejection_codes(config: dict[str, Any]) -> list[str]:
    rejected: list[str] = []
    if unknown_config_keys(config):
        rejected.append("provider_config_unknown_keys")
    if invalid_config_values(config):
        rejected.append("provider_config_invalid")
    if _config_unsanitized(config):
        rejected.append("provider_config_unsanitized")
    if remote_config_endpoints(config):
        rejected.append("cloud_endpoint_detected")
    if config.get("cloud_fallback_allowed") is not False:
        rejected.append("cloud_fallback_not_disproven")
    return rejected


def _config_quarantine_codes(config: dict[str, Any]) -> list[str]:
    if config.get("no_cloud") is True:
        return []
    return ["no_cloud_evidence_missing"]


def config_reasons(config: Any) -> tuple[list[str], list[str]]:
    if not isinstance(config, dict):
        return [], ["provider_config_missing"]
    return _config_rejection_codes(config), _config_quarantine_codes(config)
