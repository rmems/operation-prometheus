"""Load, write, and scan GitHub page cassette documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from validate_jsonl import load_schema

from .github_client import GitHubError
from .secrets import find_secrets

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None

CASSETTE_SCHEMA_VERSION = "github_page_cassette_v1"
CASSETTE_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent / "schemas" / "github_page_cassette.schema.json"
)

_LEAK_MARKERS: tuple[tuple[str, str], ...] = (
    ("authorization", "authorization_header"),
    ("bearer ", "bearer_token"),
    ("set-cookie", "cookie"),
    ('"cookie"', "cookie"),
)


def _duplicate_key(page: dict[str, Any]) -> tuple[Any, ...]:
    return (page.get("kind"), page.get("method"), page.get("url"), page.get("identity", {}).get("body_sha256"))


def mark_duplicates(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flag later pages that replay the same kind/url/body as an earlier one."""
    seen: dict[tuple[Any, ...], int] = {}
    out: list[dict[str, Any]] = []
    for seq, page in enumerate(pages):
        item = dict(page)
        item["seq"] = seq
        key = _duplicate_key(item)
        first = seen.get(key)
        if first is None:
            seen[key] = seq
            item["duplicate"] = False
            item["duplicate_of"] = None
        else:
            item["duplicate"] = True
            item["duplicate_of"] = first
        out.append(item)
    return out


def cassette_dict(pages: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = mark_duplicates(list(pages))
    return {
        "schema_version": CASSETTE_SCHEMA_VERSION,
        "page_count": len(ordered),
        "pages": ordered,
    }


def dumps_cassette(pages: list[dict[str, Any]]) -> str:
    payload = cassette_dict(pages)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def load_cassette(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_cassette(payload)
    payload["pages"] = mark_duplicates(list(payload["pages"]))
    return payload


def validate_cassette(payload: object) -> dict[str, Any]:
    cassette = _require_cassette_object(payload)
    pages = _require_page_list(cassette)
    _require_schema_version(cassette)
    _require_page_count(cassette, pages)
    _require_schema_match(cassette)
    return cassette


def _require_cassette_object(payload: object) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    raise GitHubError("GitHub page cassette must be an object")


def _require_page_list(payload: dict[str, Any]) -> list[Any]:
    pages = payload.get("pages")
    if isinstance(pages, list):
        return pages
    raise GitHubError("GitHub page cassette is missing pages")


def _require_schema_version(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") == CASSETTE_SCHEMA_VERSION:
        return
    raise GitHubError("GitHub page cassette schema_version is not github_page_cassette_v1")


def _require_page_count(payload: dict[str, Any], pages: list[Any]) -> None:
    if payload.get("page_count") == len(pages):
        return
    raise GitHubError("GitHub page cassette page_count does not match pages")


def _require_schema_match(payload: dict[str, Any]) -> None:
    if jsonschema is None:
        raise GitHubError("jsonschema is required. Install with: pip install jsonschema")
    validator = jsonschema.Draft7Validator(load_schema(CASSETTE_SCHEMA_PATH))
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
    if errors:
        raise GitHubError(f"GitHub page cassette schema: {errors[0].message}")


def write_cassette(path: Path, pages: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_cassette(pages), encoding="utf-8")
    return path


def scan_cassette_secrets(payload: dict[str, Any] | str) -> list[str]:
    """Return secret-pattern hits and credential-header leaks in a cassette dump."""
    text = payload if isinstance(payload, str) else _cassette_text(payload)
    hits = list(find_secrets(text))
    lowered = text.lower()
    for needle, name in _LEAK_MARKERS:
        if needle in lowered and name not in hits:
            hits.append(name)
    return hits


def _cassette_text(payload: dict[str, Any]) -> str:
    pages = payload.get("pages") if isinstance(payload, dict) else []
    return dumps_cassette(list(pages or []))
