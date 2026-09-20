"""Card and manifest declaration maps for source-license closure."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .license_closure_ids import _sha256_or_none, _text
from .license_closure_inventory_license import (
    _declared_license_id,
)


def _folded_mapping(mapped: Any) -> dict[str, Any]:
    if not isinstance(mapped, dict):
        return {}
    return {_text(key).casefold(): value for key, value in mapped.items() if _text(key)}


def _malformed_plural_field(container: dict[str, Any], plural: str) -> bool:
    if plural not in container:
        return False
    return not isinstance(container.get(plural), dict)


def _declared_values_conflict(previous: str | None, coerced: str | None) -> bool:
    if previous is None or coerced is None:
        return previous != coerced
    return previous.casefold() != coerced.casefold()


def _folded_value_conflicts(mapped: Any, coerce: Callable[[Any], str | None]) -> bool:
    if not isinstance(mapped, dict):
        return False
    seen: dict[str, str | None] = {}
    for key, value in mapped.items():
        folded = _text(key).casefold()
        if not folded:
            continue
        coerced = coerce(value)
        if folded not in seen:
            seen[folded] = coerced
            continue
        if _declared_values_conflict(seen[folded], coerced):
            return True
    return False


_MappingSpec = tuple[str, str, Callable[[Any], str | None]]


def _mapped_value_for_names(
    container: dict[str, Any], names: list[str], spec: _MappingSpec
) -> str | None:
    singular, plural, coerce = spec
    folded = _folded_mapping(container.get(plural))
    for name in names:
        if not name or name.casefold() not in folded:
            continue
        found = coerce(folded.get(name.casefold()))
        if found is not None:
            return found
    return coerce(container.get(singular))


def _alias_group_value_conflicts(
    mapped: Any,
    names: list[str],
    coerce: Callable[[Any], str | None],
) -> bool:
    if not isinstance(mapped, dict):
        return False
    folded = _folded_mapping(mapped)
    seen: list[str | None] = []
    for name in names:
        if not name or name.casefold() not in folded:
            continue
        coerced = coerce(folded[name.casefold()])
        seen.append(None if coerced is None else coerced.casefold())
    return len(set(seen)) > 1


def _malformed_present_value(
    container: dict[str, Any],
    key: str,
    coerce: Callable[[Any], str | None],
) -> bool:
    if key not in container:
        return False
    value = container.get(key)
    if value is None:
        return False
    return coerce(value) is None


def _singular_map_conflict(
    container: dict[str, Any], repo: str, spec: _MappingSpec
) -> bool:
    singular, plural, coerce = spec
    if _malformed_present_value(container, singular, coerce):
        return True
    folded = _folded_mapping(container.get(plural))
    if repo.casefold() not in folded:
        return False
    mapped_value = coerce(folded.get(repo.casefold()))
    singular_value = coerce(container.get(singular))
    if singular_value is None:
        return False
    if mapped_value is None:
        return True
    return mapped_value.casefold() != singular_value.casefold()


def _digest_declaration_invalid(container: dict[str, Any], repo: str) -> bool:
    folded = _folded_mapping(container.get("license_evidence_digests"))
    candidates: list[Any] = []
    if repo.casefold() in folded:
        candidates.append(folded[repo.casefold()])
    if "license_evidence_digest" in container:
        candidates.append(container.get("license_evidence_digest"))
    return any(_sha256_or_none(value) is None for value in candidates)


def _declaration_checks(
    card: dict[str, Any], manifest: dict[str, Any]
) -> tuple[tuple[dict[str, Any], str, str, Callable[[Any], str | None]], ...]:
    return (
        (card, "source_license", "source_licenses", _declared_license_id),
        (manifest, "source_license", "source_licenses", _declared_license_id),
        (card, "license_evidence_digest", "license_evidence_digests", _sha256_or_none),
        (
            manifest,
            "license_evidence_digest",
            "license_evidence_digests",
            _sha256_or_none,
        ),
    )


def _any_digest_invalid(
    card: dict[str, Any], manifest: dict[str, Any], repos: list[str]
) -> bool:
    return any(
        _digest_declaration_invalid(container, repo)
        for container in (card, manifest)
        for repo in repos
    )


def _any_plural_malformed(
    checks: tuple[tuple[dict[str, Any], str, str, Callable[[Any], str | None]], ...]
) -> bool:
    return any(
        _malformed_plural_field(container, plural)
        for container, _singular, plural, _coerce in checks
    )


def _any_singular_conflicts(
    checks: tuple[tuple[dict[str, Any], str, str, Callable[[Any], str | None]], ...],
    repos: list[str],
) -> bool:
    return any(
        _singular_map_conflict(container, repo, (singular, plural, coerce))
        for container, singular, plural, coerce in checks
        for repo in repos
    )


def _any_folded_conflicts(
    checks: tuple[tuple[dict[str, Any], str, str, Callable[[Any], str | None]], ...]
) -> bool:
    return any(
        _folded_value_conflicts(container.get(plural), coerce)
        for container, _singular, plural, coerce in checks
    )


def _any_alias_group_conflicts(
    checks: tuple[tuple[dict[str, Any], str, str, Callable[[Any], str | None]], ...],
    repos: list[str],
) -> bool:
    return any(
        _alias_group_value_conflicts(container.get(plural), repos, coerce)
        for container, _singular, plural, coerce in checks
    )


def _declaration_map_conflicts(
    card: dict[str, Any], manifest: dict[str, Any], names: list[str]
) -> bool:
    repos = [name for name in names if name] or [""]
    checks = _declaration_checks(card, manifest)
    if _any_digest_invalid(card, manifest, repos):
        return True
    if _any_plural_malformed(checks):
        return True
    if _any_singular_conflicts(checks, repos):
        return True
    if _any_folded_conflicts(checks):
        return True
    return _any_alias_group_conflicts(checks, repos)


def _mapping_license(
    container: dict[str, Any], names: list[str], singular: str, plural: str
) -> str | None:
    return _mapped_value_for_names(
        container, names, (singular, plural, _declared_license_id)
    )


def _mapping_digest(
    container: dict[str, Any], names: list[str], singular: str, plural: str
) -> str | None:
    return _mapped_value_for_names(
        container, names, (singular, plural, _sha256_or_none)
    )


def card_license_for_repo(card: dict[str, Any], names: list[str]) -> str | None:
    return _mapping_license(card, names, "source_license", "source_licenses")


def manifest_license_for_repo(manifest: dict[str, Any], names: list[str]) -> str | None:
    return _mapping_license(manifest, names, "source_license", "source_licenses")


def declared_digest_for_repo(container: dict[str, Any], names: list[str]) -> str | None:
    return _mapping_digest(
        container,
        names,
        "license_evidence_digest",
        "license_evidence_digests",
    )
