"""Builders for license-closure validator tests."""

from __future__ import annotations

from typing import Any

from lib.license_closure import evidence_digest, license_evidence_payload

SNAPSHOT_SHA256 = "a" * 64
SOURCE_HASH = "b" * 64
CUSTOM_TEXT_SHA256 = "c" * 64
STALE_DIGEST = "d" * 64


def repository(
    name: str,
    *,
    spdx_id: str | None,
    license_name: str | None = None,
    url: str | None = None,
    custom: dict[str, Any] | None = None,
    source_hash: str = SOURCE_HASH,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "name_with_owner": name,
        "source_hash": source_hash,
        "license": {"spdx_id": spdx_id, "name": license_name or spdx_id, "url": url},
    }
    if custom is not None:
        row["custom_license"] = custom
    return row


def record(
    repo: str,
    pr_number: int,
    license_id: str | None,
    *,
    record_id: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": record_id or f"{repo.replace('/', '-')}-{pr_number}",
        "repo": repo,
        "pr_number": pr_number,
        "source_urls": [f"https://github.com/{repo}/pull/{pr_number}"],
    }
    if license_id is not None:
        row["license"] = license_id
    return row


def card(
    repo: str | list[str],
    license_id: str | dict[str, str] | None,
    *,
    digest: str | dict[str, str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"name": "fixture"}
    if isinstance(repo, list):
        payload["source_repos"] = repo
    else:
        payload["source_repo"] = repo
    if isinstance(license_id, dict):
        payload["source_licenses"] = license_id
    elif license_id is not None:
        payload["source_license"] = license_id
    if isinstance(digest, dict):
        payload["license_evidence_digests"] = digest
    elif digest is not None:
        payload["license_evidence_digest"] = digest
    return payload


def manifest(
    repo: str | list[str],
    license_id: str | dict[str, str] | None,
    *,
    digest: str | dict[str, str] | None = None,
    families: list[str] | None = None,
    unresolved: int | None = None,
) -> dict[str, Any]:
    payload = card(repo, license_id, digest=digest)
    if families is not None:
        payload["license_families"] = families
    if unresolved is not None:
        payload["unresolved_license_count"] = unresolved
    return payload


def digest_for(repo_row: dict[str, Any], snapshot_sha256: str = SNAPSHOT_SHA256) -> str:
    return evidence_digest(license_evidence_payload(repo_row, snapshot_sha256=snapshot_sha256))


def spdx_known_bundle() -> dict[str, Any]:
    repo = repository(
        "rmems/widget",
        spdx_id="MIT",
        license_name="MIT License",
        url="https://api.github.com/licenses/mit",
    )
    digest = digest_for(repo)
    return {
        "card": card("rmems/widget", "MIT", digest=digest),
        "manifest": manifest(
            "rmems/widget",
            "MIT",
            digest=digest,
            families=["spdx"],
            unresolved=0,
        ),
        "markdown": (
            "## License / provenance\n\n"
            "- **Source repository license:** MIT (rmems/widget)\n"
        ),
        "prior_repositories": None,
        "records": [record("rmems/widget", 1, "MIT")],
        "repositories": [repo],
        "snapshot_sha256": SNAPSHOT_SHA256,
    }


def custom_license_bundle() -> dict[str, Any]:
    identifier = "LicenseRef-TemporalFocus"
    repo = repository(
        "rmems/TemporalFocus.jl",
        spdx_id=identifier,
        license_name="TemporalFocus custom license",
        custom={
            "identifier": identifier,
            "name": "TemporalFocus custom license",
            "text_sha256": CUSTOM_TEXT_SHA256,
        },
    )
    digest = digest_for(repo)
    return {
        "card": card("rmems/TemporalFocus.jl", identifier, digest=digest),
        "manifest": manifest(
            "rmems/TemporalFocus.jl",
            identifier,
            digest=digest,
            families=["custom"],
            unresolved=0,
        ),
        "markdown": None,
        "prior_repositories": None,
        "records": [record("rmems/TemporalFocus.jl", 7, identifier)],
        "repositories": [repo],
        "snapshot_sha256": SNAPSHOT_SHA256,
    }


def missing_license_bundle() -> dict[str, Any]:
    repo = repository("rmems/unlicensed", spdx_id=None, license_name=None)
    return {
        "card": card("rmems/unlicensed", None),
        "manifest": manifest("rmems/unlicensed", None),
        "markdown": None,
        "prior_repositories": None,
        "records": [record("rmems/unlicensed", 3, None)],
        "repositories": [repo],
        "snapshot_sha256": SNAPSHOT_SHA256,
    }


def changed_license_bundle() -> dict[str, Any]:
    prior = repository(
        "rmems/widget",
        spdx_id="MIT",
        license_name="MIT License",
        url="https://api.github.com/licenses/mit",
    )
    current = repository(
        "rmems/widget",
        spdx_id="Apache-2.0",
        license_name="Apache License 2.0",
        url="https://api.github.com/licenses/apache-2.0",
    )
    digest = digest_for(current)
    return {
        "card": card("rmems/widget", "Apache-2.0", digest=digest),
        "manifest": manifest("rmems/widget", "Apache-2.0", digest=digest),
        "markdown": None,
        "prior_repositories": None,
        "records": [record("rmems/widget", 1, "Apache-2.0")],
        "repositories": [current],
        "snapshot_sha256": SNAPSHOT_SHA256,
    }


def stale_digest_bundle() -> dict[str, Any]:
    repo = repository("rmems/widget", spdx_id="MIT", license_name="MIT License")
    return {
        "card": card("rmems/widget", "MIT", digest=STALE_DIGEST),
        "manifest": manifest("rmems/widget", "MIT", digest=STALE_DIGEST),
        "markdown": None,
        "prior_repositories": None,
        "records": [record("rmems/widget", 1, "MIT")],
        "repositories": [repo],
        "snapshot_sha256": SNAPSHOT_SHA256,
    }


def conflicting_card_manifest_bundle() -> dict[str, Any]:
    repo = repository("rmems/widget", spdx_id="MIT", license_name="MIT License")
    digest = digest_for(repo)
    return {
        "card": card("rmems/widget", "MIT", digest=digest),
        "manifest": manifest("rmems/widget", "Apache-2.0", digest=digest),
        "markdown": None,
        "prior_repositories": None,
        "records": [record("rmems/widget", 1, "MIT")],
        "repositories": [repo],
        "snapshot_sha256": SNAPSHOT_SHA256,
    }


def mixed_repository_bundle() -> dict[str, Any]:
    mit = repository(
        "rmems/widget",
        spdx_id="MIT",
        license_name="MIT License",
        url="https://api.github.com/licenses/mit",
    )
    apache = repository(
        "Limen-Neural/axon-encoder",
        spdx_id="Apache-2.0",
        license_name="Apache License 2.0",
        url="https://api.github.com/licenses/apache-2.0",
    )
    licenses = {
        "rmems/widget": "MIT",
        "Limen-Neural/axon-encoder": "Apache-2.0",
    }
    digests = {
        "rmems/widget": digest_for(mit),
        "Limen-Neural/axon-encoder": digest_for(apache),
    }
    repos = ["rmems/widget", "Limen-Neural/axon-encoder"]
    return {
        "card": card(repos, licenses, digest=digests),
        "manifest": manifest(
            repos,
            licenses,
            digest=digests,
            families=["spdx"],
            unresolved=0,
        ),
        "markdown": None,
        "prior_repositories": None,
        "records": [
            record("rmems/widget", 1, "MIT"),
            record("Limen-Neural/axon-encoder", 37, "Apache-2.0"),
        ],
        "repositories": [mit, apache],
        "snapshot_sha256": SNAPSHOT_SHA256,
    }


def unknown_license_bundle() -> dict[str, Any]:
    repo = repository("rmems/mystery", spdx_id="NOASSERTION", license_name="Other")
    return {
        "card": card("rmems/mystery", "NOASSERTION"),
        "manifest": manifest("rmems/mystery", "NOASSERTION"),
        "markdown": None,
        "prior_repositories": None,
        "records": [record("rmems/mystery", 4, "NOASSERTION")],
        "repositories": [repo],
        "snapshot_sha256": SNAPSHOT_SHA256,
    }


def forge_substitution_bundle() -> dict[str, Any]:
    repo = repository("rmems/unlicensed", spdx_id=None, license_name=None)
    return {
        "card": card("rmems/unlicensed", "Apache-2.0"),
        "manifest": manifest("rmems/unlicensed", "Apache-2.0"),
        "markdown": None,
        "prior_repositories": None,
        "records": [record("rmems/unlicensed", 9, "Apache-2.0")],
        "repositories": [repo],
        "snapshot_sha256": SNAPSHOT_SHA256,
    }


def apache_source_bundle() -> dict[str, Any]:
    """Source repository is genuinely Apache-2.0; that is not a relicense."""
    repo = repository(
        "rmems/corinth-canal",
        spdx_id="Apache-2.0",
        license_name="Apache License 2.0",
        url="https://api.github.com/licenses/apache-2.0",
    )
    digest = digest_for(repo)
    return {
        "card": card("rmems/corinth-canal", "Apache-2.0", digest=digest),
        "manifest": manifest(
            "rmems/corinth-canal",
            "Apache-2.0",
            digest=digest,
            families=["spdx"],
            unresolved=0,
        ),
        "markdown": None,
        "prior_repositories": None,
        "records": [record("rmems/corinth-canal", 142, "Apache-2.0")],
        "repositories": [repo],
        "snapshot_sha256": SNAPSHOT_SHA256,
    }


def report_kwargs(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "card": bundle["card"],
        "manifest": bundle["manifest"],
        "markdown_card": bundle["markdown"],
        "prior_repositories": bundle["prior_repositories"],
        "records": bundle["records"],
        "repositories": bundle["repositories"],
        "snapshot_sha256": bundle["snapshot_sha256"],
    }
