"""URI and private-reference policy helpers for CI contracts."""

from __future__ import annotations

import ipaddress
import re
from typing import Any
from urllib.parse import urlparse

PRIVATE_HOST_RE = re.compile(
    r"(?i)^(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+"
    r"|172\.(?:1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+|.*\.(?:internal|lan))$"
)


def _string_fields(record: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    for key in keys:
        field = record.get(key)
        if isinstance(field, list):
            values.extend(item for item in field if isinstance(item, str))
        elif isinstance(field, str):
            values.append(field)
    return values


def _artifact_uri(artifact: Any) -> str | None:
    if not isinstance(artifact, dict):
        return None
    uri = artifact.get("uri")
    if isinstance(uri, str):
        return uri
    return None


def _event_evidence_uris(event: Any) -> list[str]:
    if not isinstance(event, dict):
        return []
    return _string_fields(event, ("evidence_references",))


def _append_artifact_uris(record: dict[str, Any], values: list[str]) -> None:
    for artifact in record.get("artifacts") or []:
        uri = _artifact_uri(artifact)
        if uri is not None:
            values.append(uri)


def _append_event_uris(record: dict[str, Any], values: list[str]) -> None:
    for event in record.get("events") or []:
        values.extend(_event_evidence_uris(event))


def iter_uri_fields(record: dict[str, Any]) -> list[str]:
    """Yield sourced URI strings, excluding patch bodies and review prose."""
    values = _string_fields(
        record, ("source_urls", "evidence_references", "url", "uri", "html_url")
    )
    _append_artifact_uris(record, values)
    _append_event_uris(record, values)
    return values


def _is_private_host(host: str) -> bool:
    try:
        return not ipaddress.ip_address(host).is_global
    except ValueError:
        return bool(PRIVATE_HOST_RE.fullmatch(host))


def _uri_policy_hit(token: str) -> str | None:
    try:
        parsed = urlparse(token)
    except ValueError:
        return None
    scheme = (parsed.scheme or "").casefold()
    if scheme == "file":
        return "private file URI"
    if scheme in {"ssh", "git"}:
        return "private or ssh git URI"
    host = (parsed.hostname or "").casefold()
    if not host:
        return None
    if _is_private_host(host):
        return f"private host {host}"
    return None


def private_reference_errors(text: str) -> list[str]:
    """Return policy hits for URI-like private or non-public references."""
    errors: list[str] = []
    for match in re.finditer(
        r"\b(?:[a-z][a-z0-9+.-]*:|/+)[^\s\"'<>]+", text, re.IGNORECASE
    ):
        hit = _uri_policy_hit(match.group(0))
        if hit is not None:
            errors.append(hit)
    if re.search(r"(?i)\bgit@[^\s:]+:", text):
        errors.append("ssh git@ remote")
    return errors
