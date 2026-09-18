"""Bundle declaration checks for license-closure reports."""

from __future__ import annotations

from typing import Any

from .license_closure_ids import LICENSE_FAMILIES, _sha256_or_none, _text


def _declared_count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _released_evidence_summary(
    released: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    families = sorted({row["license_family"] for row in released})
    keys = sorted(
        {
            (
                row["repo"],
                row["evidence_digest"],
                row["license_family"],
                row.get("spdx_id") or "",
            )
            for row in released
        }
    )
    evidence = [
        {
            "digest": digest,
            "family": family,
            "repository": repo,
            "spdx_id": spdx_id or None,
        }
        for repo, digest, family, spdx_id in keys
    ]
    return families, evidence


def _declared_families_invalid(declared: Any, expected: list[str]) -> bool:
    if not isinstance(declared, list):
        return True
    if any(
        not isinstance(item, str) or item not in LICENSE_FAMILIES for item in declared
    ):
        return True
    return sorted(declared) != expected


def _bundle_declaration_errors(
    report: dict[str, Any], manifest: dict[str, Any], card: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    errors.extend(_family_bundle_errors(report, card, manifest))
    errors.extend(_unresolved_bundle_errors(report, card, manifest))
    errors.extend(_digest_bundle_errors(report, manifest))
    errors.extend(_record_bundle_errors(report, manifest))
    return errors


def _family_bundle_errors(
    report: dict[str, Any], card: dict[str, Any], manifest: dict[str, Any]
) -> list[str]:
    for source in (card, manifest):
        declared_families = source.get("license_families")
        if declared_families is None:
            continue
        if _declared_families_invalid(declared_families, report["license_families"]):
            return ["card/manifest license_families do not agree with closed evidence"]
    return []


def _unresolved_bundle_errors(
    report: dict[str, Any], card: dict[str, Any], manifest: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    for source, label in ((card, "card"), (manifest, "manifest")):
        unresolved = source.get("unresolved_license_count")
        if unresolved is None:
            continue
        if _declared_count(unresolved) != report["counts"]["unresolved_count"]:
            errors.append(
                f"{label} unresolved_license_count does not agree with closure result"
            )
    return errors


def _digest_bundle_errors(report: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    declared_digests = manifest.get("license_evidence_digests")
    if not isinstance(declared_digests, dict):
        return []
    observed = {
        row["repository"].casefold(): row["digest"] for row in report["evidence_digests"]
    }
    errors: list[str] = []
    for repo, digest in declared_digests.items():
        actual = observed.get(_text(repo).casefold())
        if actual is not None and _sha256_or_none(digest) != actual:
            errors.append(
                f"manifest evidence digest for {repo} does not agree with inventory"
            )
    return errors


def _record_bundle_errors(report: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if "record_count" in manifest:
        if _declared_count(manifest["record_count"]) != report["counts"]["record_count"]:
            errors.append("manifest record_count does not agree with proposed records")
    if "records" not in manifest:
        return errors
    listed = manifest.get("records")
    actual_ids = sorted(
        row["record_id"] for row in report["released_positives"] + report["quarantined"]
    )
    declared_ids, malformed = _listed_record_ids(listed)
    if malformed or sorted(declared_ids) != actual_ids:
        errors.append("manifest record ids do not agree with proposed records")
    return errors


def _listed_record_ids(listed: object) -> tuple[list[str], bool]:
    if not isinstance(listed, list):
        return [], True
    declared_ids: list[str] = []
    for row in listed:
        rid = _text(row.get("id")) if isinstance(row, dict) else ""
        if not rid:
            return declared_ids, True
        declared_ids.append(rid)
    return declared_ids, False
