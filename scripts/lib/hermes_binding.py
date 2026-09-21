"""Manifest, admission, and schema bindings for Hermes normalization."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from validate_jsonl import load_schema

from .source_inventory_common import sha256_json

try:
    import jsonschema
except ImportError:  # pragma: no cover - exercised at CLI startup
    jsonschema = None

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
V1_1_SCHEMA_PATH = REPO_ROOT / "schemas" / "trajectory_v1_1.schema.json"
MANIFEST_SCHEMA_PATH = REPO_ROOT / "schemas" / "hermes_run_manifest.schema.json"
RAW_SCHEMA_PATH = REPO_ROOT / "schemas" / "hermes_raw_trace.schema.json"
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _object_fields(value: Any, fields: tuple[str, ...]) -> bool:
    if not isinstance(value, dict):
        return False
    return all(_nonempty_str(value.get(field)) for field in fields)


_MODEL_BIND_FIELDS = (
    "name",
    "tag",
    "ollama_digest",
    "quantization",
    "upstream_revision",
)
_OPTIONAL_MODEL_FIELDS = frozenset({"quantization", "upstream_revision"})
_REQUIRED_INPUT_DIGESTS = ("admissions", "rights", "probe")


def _present(value: Any) -> bool:
    return value is not None and value != ""


def _evidence_digest_ok(admission: dict[str, Any]) -> bool:
    declared = admission.get("evidence_digest")
    if not _is_sha256(declared):
        return False
    body = {key: value for key, value in admission.items() if key != "evidence_digest"}
    return declared == sha256_json(body)


def _fallback_disproved(admission: dict[str, Any]) -> bool:
    provider = admission.get("provider")
    config = provider.get("config") if isinstance(provider, dict) else None
    fallback = admission.get("fallback_evidence")
    if not isinstance(config, dict) or not isinstance(fallback, dict):
        return False
    return (
        admission.get("cloud_fallback_allowed") is False
        and config.get("no_cloud") is True
        and config.get("cloud_fallback_allowed") is False
        and fallback.get("no_cloud") is True
        and fallback.get("cloud_fallback_allowed") is False
        and fallback.get("unsanitized_keys") == []
        and fallback.get("remote_endpoints") == []
    )


def _workspace_errors(manifest: dict[str, Any]) -> list[str]:
    workspace = manifest.get("workspace")
    if not isinstance(workspace, dict):
        return ["workspace_not_isolated"]
    if not _nonempty_str(workspace.get("id")) or workspace.get("kind") != "isolated":
        return ["workspace_not_isolated"]
    return []


def _binding_errors(
    manifest: dict[str, Any], admission: dict[str, Any], admission_digest: str
) -> list[str]:
    reasons = _admission_envelope_errors(manifest, admission, admission_digest)
    reasons.extend(_admission_component_errors(manifest, admission))
    reasons.extend(_cross_bind_errors(manifest, admission))
    return reasons


def _admission_envelope_errors(
    manifest: dict[str, Any], admission: dict[str, Any], admission_digest: str
) -> list[str]:
    checks = (
        (
            str(manifest.get("admission_report_sha256") or "") != admission_digest,
            "admission_digest_mismatch",
        ),
        (
            admission.get("schema_version") != "local_model_admission_v1",
            "admission_schema",
        ),
        (admission.get("decision") != "accepted", "admission_rejected"),
        (admission.get("reasons") != [], "admission_reasons"),
        (not _evidence_digest_ok(admission), "evidence_digest"),
    )
    return [reason for failed, reason in checks if failed]


def _admission_component_errors(
    manifest: dict[str, Any], admission: dict[str, Any]
) -> list[str]:
    reasons: list[str] = []
    model = admission.get("model")
    runtime = admission.get("runtime")
    rights = admission.get("rights")
    provider = admission.get("provider")
    probe = admission.get("probe")
    digests = admission.get("input_digests")
    if not _model_valid(model):
        reasons.append("admission_schema")
    if not _object_fields(runtime, ("name", "version", "endpoint")):
        reasons.append("admission_schema")
    reasons.extend(_rights_errors(manifest, rights, digests))
    if not isinstance(provider, dict) or provider.get("name") != "hermes-agent":
        reasons.append("provider_mismatch")
    if not _object_fields(probe, ("timestamp", "endpoint")):
        reasons.append("admission_schema")
    if not isinstance(digests, dict) or any(
        not _is_sha256(digests.get(name)) for name in _REQUIRED_INPUT_DIGESTS
    ):
        reasons.append("admission_schema")
    if not _fallback_disproved(admission):
        reasons.append("cloud_fallback")
    return reasons


def _model_valid(model: Any) -> bool:
    if not _object_fields(model, ("name", "tag", "ollama_digest", "quantization")):
        return False
    upstream = model.get("upstream_revision")
    return (
        "upstream_revision" not in model or upstream is None or _nonempty_str(upstream)
    )


def _rights_errors(manifest: dict[str, Any], rights: Any, digests: Any) -> list[str]:
    if not _object_fields(rights, ("identifier", "terms_source", "terms_sha256")):
        return ["admission_schema"]
    if rights.get("identifier") != manifest.get("output_license"):
        return ["rights_mismatch"]
    if not isinstance(digests, dict) or rights.get("terms_sha256") != digests.get(
        "rights"
    ):
        return ["rights_mismatch"]
    return []


def _cross_bind_errors(
    manifest: dict[str, Any], admission: dict[str, Any]
) -> list[str]:
    return [
        *_model_bind_errors(manifest, admission),
        *_runtime_bind_errors(manifest, admission),
        *_provider_bind_errors(manifest, admission),
    ]


def _model_bind_errors(
    manifest: dict[str, Any], admission: dict[str, Any]
) -> list[str]:
    manifest_model = (
        manifest.get("model") if isinstance(manifest.get("model"), dict) else {}
    )
    admission_model = (
        admission.get("model") if isinstance(admission.get("model"), dict) else {}
    )
    for field in _MODEL_BIND_FIELDS:
        left = manifest_model.get(field)
        right = admission_model.get(field)
        if (
            field in _OPTIONAL_MODEL_FIELDS
            and not _present(left)
            and not _present(right)
        ):
            continue
        if left != right:
            return ["model_mismatch"]
    return []


def _runtime_bind_errors(
    manifest: dict[str, Any], admission: dict[str, Any]
) -> list[str]:
    ollama = manifest.get("ollama") if isinstance(manifest.get("ollama"), dict) else {}
    runtime = (
        admission.get("runtime") if isinstance(admission.get("runtime"), dict) else {}
    )
    runtime_mismatch = (
        runtime.get("name") != ollama.get("runtime")
        or runtime.get("version") != ollama.get("version")
        or runtime.get("endpoint") != ollama.get("endpoint")
    )
    probe = admission.get("probe") if isinstance(admission.get("probe"), dict) else {}
    probe_mismatch = probe.get("endpoint") not in {
        runtime.get("endpoint"),
        ollama.get("endpoint"),
    } or runtime.get("endpoint") != ollama.get("endpoint")
    return [
        *(["runtime_mismatch"] if runtime_mismatch else []),
        *(["probe_endpoint_mismatch"] if probe_mismatch else []),
    ]


def _provider_bind_errors(
    manifest: dict[str, Any], admission: dict[str, Any]
) -> list[str]:
    producer = (
        manifest.get("producer") if isinstance(manifest.get("producer"), dict) else {}
    )
    provider = (
        admission.get("provider") if isinstance(admission.get("provider"), dict) else {}
    )
    if provider.get("name") != producer.get("name"):
        return ["provider_mismatch"]
    return []


def _schema_reason(document: Any, schema_path: Path, code: str) -> list[str]:
    if jsonschema is None:
        return ["jsonschema_missing"]
    validator = jsonschema.Draft7Validator(
        load_schema(schema_path),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    if errors:
        return [code]
    return []


def _manifest_schema_errors(manifest: dict[str, Any]) -> list[str]:
    return _schema_reason(manifest, MANIFEST_SCHEMA_PATH, "invalid_manifest")


def _raw_record_errors(record: dict[str, Any], validator: Any) -> list[str]:
    if validator is None:
        return ["jsonschema_missing"]
    errors = sorted(validator.iter_errors(record), key=lambda item: list(item.path))
    if errors:
        return ["invalid_hermes_record"]
    return []


def _v1_1_validator() -> Any:
    if jsonschema is None:
        return None
    return jsonschema.Draft7Validator(
        load_schema(V1_1_SCHEMA_PATH),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )


def _raw_validator() -> Any:
    if jsonschema is None:
        return None
    return jsonschema.Draft7Validator(
        load_schema(RAW_SCHEMA_PATH),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )
