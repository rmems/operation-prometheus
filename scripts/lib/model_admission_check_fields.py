"""Field-level checks for local-model admission candidates."""

from __future__ import annotations

from typing import Any

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


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


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
