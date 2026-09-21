"""Field-level checks for local-model admission candidates."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .model_admission_evidence import (
    endpoint_host,
    is_loopback_endpoint,
    remote_config_endpoints,
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
    if endpoint_host(endpoint) is None:
        return [], ["endpoint_invalid"]
    if not is_loopback_endpoint(endpoint):
        return ["endpoint_not_loopback"], []
    return [], []


def config_reasons(config: Any) -> tuple[list[str], list[str]]:
    if not isinstance(config, dict):
        return [], ["provider_config_missing"]
    rejected: list[str] = []
    if unsanitized_config_keys(config):
        rejected.append("provider_config_unsanitized")
    if remote_config_endpoints(config):
        rejected.append("cloud_endpoint_detected")
    quarantined = (
        [] if config.get("no_cloud") is True else ["no_cloud_evidence_missing"]
    )
    return rejected, quarantined


def timestamp_reasons(candidate: dict[str, Any]) -> tuple[list[str], list[str]]:
    value = candidate.get("probed_at")
    if value is None:
        return [], ["probe_timestamp_missing"]
    if not isinstance(value, str):
        return [], ["probe_timestamp_invalid"]
    try:
        datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return [], ["probe_timestamp_invalid"]
    return [], []
