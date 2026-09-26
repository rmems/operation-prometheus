"""Evidence primitives for local-model admission.

One strict JSON parser for frozen and live JSON (duplicate keys and non-finite
numbers rejected), canonical SHA-256 digests, deterministic report rendering,
canonical loopback endpoint validation, provider-config sanitization with a
strict key allowlist, and frozen-input collision protection.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .source_inventory_common import canonical_json_bytes

SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
OLLAMA_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
RFC3339_TZ_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
LOOPBACK_SCHEMES = frozenset({"http"})

# Strict provider-config allowlist: only Ollama generation/runtime knobs.
ALLOWED_CONFIG_KEYS = frozenset(
    {
        "no_cloud",
        "cloud_fallback_allowed",
        "num_ctx",
        "num_predict",
        "num_gpu",
        "num_thread",
        "num_batch",
        "temperature",
        "top_k",
        "top_p",
        "min_p",
        "tfs_z",
        "typical_p",
        "seed",
        "keep_alive",
        "repeat_penalty",
        "presence_penalty",
        "frequency_penalty",
        "mirostat",
        "mirostat_eta",
        "mirostat_tau",
        "stop",
    }
)

# Allowed value types per allowlisted provider-config key.
CONFIG_KEY_TYPES = {
    "no_cloud": "bool",
    "cloud_fallback_allowed": "bool",
    "seed": "int",
    "mirostat": "int",
    "keep_alive": "str",
    "stop": "str_list",
}

_SECRET_VALUE_RE = re.compile(
    r"ghp_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|sk-(?:proj-)?[A-Za-z0-9_-]{20,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|AIza[0-9A-Za-z_-]{20,}"
    r"|Bearer\s+[A-Za-z0-9._-]{10,}"
)

_SECRET_KEY_RE = re.compile(
    r"api[-_]?key|token|secret|password|passwd|authorization|credential",
    re.IGNORECASE,
)
_ENDPOINT_KEYS = frozenset(
    {
        "base_url",
        "endpoint",
        "host",
        "url",
        "api_base",
        "fallback_url",
        "remote_url",
        "server",
    }
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def sha256_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    return text if SHA256_RE.fullmatch(text) else None


def ollama_digest_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text if OLLAMA_DIGEST_RE.fullmatch(text) else None


def _reject_nonfinite(constant: str) -> None:
    raise json.JSONDecodeError(f"non-finite constant {constant!r}", constant, 0)


def _parse_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"non-finite number {value!r}")
    return number


def _object_pairs(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    result: dict[str, Any] = {}
    for key, value in pairs:
        name = key if isinstance(key, str) else str(key)
        if name in seen:
            raise json.JSONDecodeError(f"duplicate object key {name!r}", name, 0)
        seen.add(name)
        result[name] = value
    return result


def loads_strict(text: str) -> Any:
    """The one strict JSON parser: frozen files and live responses alike."""
    return json.loads(
        text,
        parse_constant=_reject_nonfinite,
        parse_float=_parse_float,
        object_pairs_hook=_object_pairs,
    )


def load_json_strict(path: Path) -> Any:
    return loads_strict(path.read_text(encoding="utf-8"))


def load_jsonl_strict(path: Path) -> list[Any]:
    return parse_jsonl_strict(path.read_bytes().decode("utf-8"))


def parse_jsonl_strict(text: str) -> list[Any]:
    return [loads_strict(line) for line in text.splitlines() if line.strip()]


def read_frozen_json(path: Path) -> tuple[Any, bytes]:
    """Read once: returns (parsed object, exact file bytes)."""
    data = path.read_bytes()
    return loads_strict(data.decode("utf-8")), data


def read_frozen_jsonl(path: Path) -> tuple[list[Any], bytes]:
    data = path.read_bytes()
    return parse_jsonl_strict(data.decode("utf-8")), data


def render_report(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _endpoint_text_ok(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if value != value.strip():
        return False
    return value.startswith("http://")


def _canonical_netloc(parsed) -> str | None:
    """Lowercase loopback host:port netloc, or None."""
    netloc = parsed.netloc
    if netloc != netloc.lower() or "@" in netloc:
        return None
    try:
        port = parsed.port
        host = parsed.hostname
    except ValueError:
        return None
    if host not in LOOPBACK_HOSTS or port is None:
        return None
    return netloc


def _endpoint_extras_empty(parsed) -> bool:
    """Path is empty or ``/``, and query and fragment are absent."""
    if parsed.path not in ("", "/"):
        return False
    if parsed.query:
        return False
    return not parsed.fragment


def canonical_loopback_endpoint(value: Any) -> str | None:
    """Canonical http://loopback endpoint, or None when non-canonical.

    Requires a lowercase literal ``http`` scheme and lowercase host with an
    explicit port; path must be empty or ``/``; no query, fragment, userinfo,
    or credentials. IPv6 loopback keeps its brackets
    (``http://[::1]:11434``).
    """
    if not _endpoint_text_ok(value):
        return None
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    if parsed.scheme != "http":
        return None
    if not _endpoint_extras_empty(parsed):
        return None
    netloc = _canonical_netloc(parsed)
    if netloc is None:
        return None
    return f"http://{netloc}"


def endpoint_host(endpoint: Any) -> str | None:
    """URL host for a syntactically valid http(s) endpoint, else None."""
    if not isinstance(endpoint, str) or not endpoint.strip():
        return None
    try:
        parsed = urlparse(endpoint.strip())
    except ValueError:
        return None
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        return None
    return parsed.hostname


def is_loopback_endpoint(endpoint: Any) -> bool:
    host = endpoint_host(endpoint)
    return host is not None and host in LOOPBACK_HOSTS


def parse_rfc3339_tz(value: Any) -> bool:
    """True only for a timezone-aware RFC 3339 timestamp string."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not RFC3339_TZ_RE.fullmatch(text):
        return False
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _iter_config_items(config: Any, prefix: str = ""):
    """Yield (dotted_key, value) pairs from a nested config object."""
    if not isinstance(config, dict):
        return
    for key, value in config.items():
        name = f"{prefix}{key}" if isinstance(key, str) else prefix
        yield name, value
        if isinstance(value, dict):
            yield from _iter_config_items(value, f"{name}.")


def unknown_config_keys(config: Any) -> list[str]:
    """Config paths whose segments are not all allowlisted (nesting rejects)."""
    return [
        name
        for name, _ in _iter_config_items(config)
        if not all(
            segment in ALLOWED_CONFIG_KEYS for segment in name.split(".")
        )
    ]


def invalid_config_values(config: Any) -> list[str]:
    """Leaves violating the allowed type/range for their key.

    Nested mappings are invalid (the allowlist is flat); numeric knobs must
    be finite non-negative numbers, ``seed``/``mirostat`` integers,
    ``no_cloud``/``cloud_fallback_allowed`` booleans, ``stop`` a list of
    strings, ``keep_alive`` a string.
    """
    invalid: list[str] = []
    for name, value in _iter_config_items(config):
        leaf = name.rsplit(".", 1)[-1]
        if leaf not in ALLOWED_CONFIG_KEYS:
            continue
        if isinstance(value, dict):
            invalid.append(name)
            continue
        kind = CONFIG_KEY_TYPES.get(leaf, "num")
        if not _value_matches_kind(value, kind):
            invalid.append(name)
    return invalid


def _is_strict_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_str_list(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    return all(isinstance(item, str) for item in value)


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def _is_nonnegative_number(value: Any) -> bool:
    return _is_finite_number(value) and value >= 0


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _is_str(value: Any) -> bool:
    return isinstance(value, str)


_KIND_CHECKS = {
    "bool": _is_bool,
    "int": _is_strict_int,
    "str": _is_str,
    "str_list": _is_str_list,
}


def _value_matches_kind(value: Any, kind: str) -> bool:
    check = _KIND_CHECKS.get(kind, _is_nonnegative_number)
    return check(value)


_CREDENTIAL_PARAM_RE = re.compile(
    r"(?i)(api[-_]?key|token|secret|password|credential|auth)="
)
_CREDENTIAL_HEADER_RE = re.compile(
    r'(?i)(authorization\s*:\s*(?:basic|bearer)\s+\S'
    r'|\b[a-z0-9_-]*(?:api[-_]?key|secret|token|password'
    r'|credential)\b[\x22\x27]?\s*:\s*[\x22\x27]?\S)'
)
_LOCAL_REFERENCE_RE = re.compile(r"^\s*(file://|~/|/[a-zA-Z]|[A-Za-z]:\\)")


def _credential_string(value: str) -> bool:
    """True for credential, header-shaped, or local/file-path material."""
    return bool(
        _SECRET_VALUE_RE.search(value)
        or _CREDENTIAL_PARAM_RE.search(value)
        or _CREDENTIAL_HEADER_RE.search(value)
        or _LOCAL_REFERENCE_RE.search(value)
    )


def credential_config_values(config: Any) -> list[str]:
    """Scalar values anywhere in the config matching credential patterns."""
    hits: list[str] = []
    for name, value in _iter_config_items(config):
        strings = value if isinstance(value, list) else [value]
        if any(
            isinstance(item, str) and _credential_string(item)
            for item in strings
        ):
            hits.append(name)
    return hits


def _nonempty_secret_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return isinstance(value, bool) and value


def unsanitized_config_keys(config: Any) -> list[str]:
    """Secret-looking keys carrying non-empty values in a provider config."""
    return [
        name
        for name, value in _iter_config_items(config)
        if _SECRET_KEY_RE.search(name) and _nonempty_secret_value(value)
    ]


def _is_remote_url(value: str) -> bool:
    text = value.strip()
    if not text.startswith(("http://", "https://")):
        return False
    return canonical_loopback_endpoint(text) is None


def _endpoint_or_remote(name: str, item: str) -> bool:
    if _is_remote_url(item):
        return True
    leaf_is_endpoint = name.rsplit(".", 1)[-1].lower() in _ENDPOINT_KEYS
    return leaf_is_endpoint and canonical_loopback_endpoint(item) is None


def remote_config_endpoints(config: Any) -> list[str]:
    """Remote/cloud URLs anywhere in the config (any key, including lists)."""
    return [
        item
        for name, value in _iter_config_items(config)
        for item in (value if isinstance(value, list) else [value])
        if isinstance(item, str)
        and item.strip()
        and _endpoint_or_remote(name, item)
    ]


def paths_collide(path_a: Path, path_b: Path) -> bool:
    """True when both paths name the same file (hard links and symlinks)."""
    if path_a == path_b:
        return True
    try:
        return path_a.samefile(path_b)
    except OSError:
        return False
