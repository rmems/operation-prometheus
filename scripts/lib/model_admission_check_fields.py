"""Field-level checks for local-model admission candidates."""

from __future__ import annotations

from typing import Any

import re

from .model_admission_evidence import (
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


def envelope_reasons(candidate: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Closed candidate envelope: unknown keys and foreign/secret values reject."""
    unknown = [key for key in candidate if key not in ALLOWED_CANDIDATE_KEYS]
    rejected = ["candidate_unknown_fields"] if unknown else []
    for key in unknown:
        value = candidate.get(key)
        if _looks_secret(key, value) or _looks_remote_endpoint(key, value):
            rejected.append("candidate_unsanitized")
        if key.strip().lower() in _FOREIGN_PROVIDER_HINTS:
            rejected.append("foreign_provider_declared")
    return sorted(set(rejected)), []


def _looks_secret(key: Any, value: Any) -> bool:
    from .model_admission_evidence import (
        _SECRET_KEY_RE,
        _SECRET_VALUE_RE,
        _nonempty_secret_value,
    )

    if isinstance(key, str) and _SECRET_KEY_RE.search(key):
        return _nonempty_secret_value(value)
    values = value if isinstance(value, list) else [value]
    return any(
        isinstance(item, str) and _SECRET_VALUE_RE.search(item)
        for item in values
    )


def _looks_remote_endpoint(key: Any, value: Any) -> bool:
    from .model_admission_evidence import (
        _ENDPOINT_KEYS,
        canonical_loopback_endpoint,
    )

    if not (isinstance(key, str) and key.strip().lower() in _ENDPOINT_KEYS):
        return False
    if not isinstance(value, str) or not value.strip():
        return False
    return canonical_loopback_endpoint(value) is None


def runtime_reasons(candidate: dict[str, Any]) -> tuple[list[str], list[str]]:
    runtime = _text(candidate.get("runtime"))
    if runtime is None:
        return [], ["runtime_missing"]
    if runtime != SUPPORTED_RUNTIME:
        return ["runtime_unsupported"], []
    return [], []


def endpoint_reasons(candidate: dict[str, Any]) -> tuple[list[str], list[str]]:
    endpoint = candidate.get("endpoint")
    if _text(endpoint) is None:
        return [], ["endpoint_missing"]
    host = endpoint_host(endpoint)
    if host is not None and host not in ("localhost", "127.0.0.1", "::1"):
        return ["endpoint_not_loopback"], []
    if canonical_loopback_endpoint(endpoint) is None:
        return [], ["endpoint_invalid"]
    return [], []


def config_reasons(config: Any) -> tuple[list[str], list[str]]:
    if not isinstance(config, dict):
        return [], ["provider_config_missing"]
    rejected: list[str] = []
    if unknown_config_keys(config):
        rejected.append("provider_config_unknown_keys")
    if invalid_config_values(config):
        rejected.append("provider_config_invalid")
    if unsanitized_config_keys(config) or credential_config_values(config):
        rejected.append("provider_config_unsanitized")
    if remote_config_endpoints(config):
        rejected.append("cloud_endpoint_detected")
    if config.get("cloud_fallback_allowed") is not False:
        rejected.append("cloud_fallback_not_disproven")
    quarantined = (
        [] if config.get("no_cloud") is True else ["no_cloud_evidence_missing"]
    )
    return rejected, quarantined
