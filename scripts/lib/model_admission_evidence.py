"""Evidence primitives for local-model admission.

Strict JSON loading (duplicate keys and non-finite constants rejected),
canonical SHA-256 digests, deterministic report rendering, loopback endpoint
checks, provider-config sanitization, and frozen-input collision protection.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .source_inventory_common import canonical_json_bytes

SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_SECRET_KEY_RE = re.compile(
    r"api[-_]?key|token|secret|password|passwd|authorization|credential",
    re.IGNORECASE,
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


def _reject_nonfinite(constant: str) -> None:
    raise json.JSONDecodeError(f"non-finite constant {constant!r}", constant, 0)


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


def load_json_strict(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=_reject_nonfinite,
        object_pairs_hook=_object_pairs,
    )


def load_jsonl_strict(path: Path) -> list[Any]:
    rows: list[Any] = []
    for line in path.read_bytes().decode("utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(
            json.loads(
                line,
                parse_constant=_reject_nonfinite,
                object_pairs_hook=_object_pairs,
            )
        )
    return rows


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


def endpoint_host(endpoint: Any) -> str | None:
    """Return the URL host for a valid http(s) endpoint, else None."""
    if not isinstance(endpoint, str) or not endpoint.strip():
        return None
    parsed = urlparse(endpoint.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    return parsed.hostname


def is_loopback_endpoint(endpoint: Any) -> bool:
    host = endpoint_host(endpoint)
    return host is not None and host in LOOPBACK_HOSTS


def _iter_config_items(config: Any, prefix: str = ""):
    """Yield (dotted_key, scalar_value) pairs from a nested config object."""
    if not isinstance(config, dict):
        return
    for key, value in config.items():
        name = f"{prefix}{key}" if isinstance(key, str) else prefix
        if isinstance(value, dict):
            yield from _iter_config_items(value, f"{name}.")
        else:
            yield name, value


def unsanitized_config_keys(config: Any) -> list[str]:
    """Secret-looking keys carrying non-empty values in a provider config."""
    return [
        name
        for name, value in _iter_config_items(config)
        if _SECRET_KEY_RE.search(name)
        and isinstance(value, str)
        and value.strip()
    ]


_ENDPOINT_KEYS = frozenset({"base_url", "endpoint", "host", "url", "api_base"})


def remote_config_endpoints(config: Any) -> list[str]:
    """base_url/endpoint/host entries that are not loopback."""
    return [
        value
        for name, value in _iter_config_items(config)
        if name.rsplit(".", 1)[-1].lower() in _ENDPOINT_KEYS
        and isinstance(value, str)
        and value.strip()
        and not is_loopback_endpoint(value)
    ]


def paths_collide(path_a: Path, path_b: Path) -> bool:
    """True when both paths name the same file (hard links and symlinks)."""
    if path_a == path_b:
        return True
    try:
        return path_a.samefile(path_b)
    except OSError:
        return False
