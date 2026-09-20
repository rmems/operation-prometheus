"""Builders for license-closure validator tests."""

from __future__ import annotations

from typing import Any

from lib.license_closure import (
    evidence_digest,
    inventory_row_source_hash,
    license_evidence_payload,
    pr_inventory_row_source_hash,
)

SNAPSHOT_SHA256 = "a" * 64
SOURCE_HASH = "b" * 64
CUSTOM_TEXT_SHA256 = "c" * 64
STALE_DIGEST = "d" * 64
BASE_OID = "1" * 40
HEAD_OID = "2" * 40
MERGE_OID = "3" * 40
WRONG_HEAD_OID = "4" * 40


def repository(
    name: str,
    *,
    spdx_id: str | None,
    license_name: str | None = None,
    url: str | None = None,
    custom: dict[str, Any] | None = None,
    source_hash: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "name_with_owner": name,
        "license": {"spdx_id": spdx_id, "name": license_name or spdx_id, "url": url},
        "visibility": "public",
    }
    if custom is not None:
        row["custom_license"] = custom
    row["source_hash"] = source_hash or inventory_row_source_hash(row)
    return row


def bind_source_hash(row: dict[str, Any]) -> dict[str, Any]:
    updated = dict(row)
    updated["source_hash"] = inventory_row_source_hash(updated)
    return updated


def bind_pr_source_hash(row: dict[str, Any]) -> dict[str, Any]:
    updated = dict(row)
    updated["source_hash"] = pr_inventory_row_source_hash(updated)
    return updated


def inventory_alias(name: str, *refs: str) -> dict[str, Any]:
    return {
        "name_with_owner": name,
        "evidence_refs": list(refs) or [f"https://github.com/{name}"],
    }


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


def with_code_state(
    row: dict[str, Any],
    *,
    base_oid: str = BASE_OID,
    head_oid: str = HEAD_OID,
    commit_oid: str = MERGE_OID,
) -> dict[str, Any]:
    updated = dict(row)
    updated["repository"] = {
        "base_oid": base_oid,
        "head_oid": head_oid,
        "commit_oid": commit_oid,
    }
    return updated


def inventory_pr(
    repo: str,
    number: int,
    *,
    base_oid: str = BASE_OID,
    head_oid: str = HEAD_OID,
    merge_commit_oid: str = MERGE_OID,
) -> dict[str, Any]:
    return bind_pr_source_hash(
        {
            "base_oid": base_oid,
            "head_oid": head_oid,
            "merge_commit_oid": merge_commit_oid,
            "number": number,
            "repository_name_with_owner": repo,
        }
    )


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


def digest_for(repo_row: dict[str, Any]) -> str:
    return evidence_digest(license_evidence_payload(repo_row))


def _bundle(
    card_payload: dict[str, Any],
    manifest_payload: dict[str, Any],
    records: list[dict[str, Any]],
    repositories: list[dict[str, Any]],
    *,
    markdown: str | None = None,
    prior_repositories: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "card": card_payload,
        "manifest": manifest_payload,
        "markdown": markdown,
        "prior_repositories": prior_repositories,
        "records": records,
        "repositories": repositories,
        "snapshot_sha256": SNAPSHOT_SHA256,
    }


def _single_repo_bundle(
    repo_name: str,
    license_id: str | None,
    repo: dict[str, Any],
    pr_number: int,
    *,
    digest: str | None = None,
    families: list[str] | None = None,
    unresolved: int | None = None,
    markdown: str | None = None,
    prior_repositories: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return _bundle(
        card(repo_name, license_id, digest=digest),
        manifest(
            repo_name,
            license_id,
            digest=digest,
            families=families,
            unresolved=unresolved,
        ),
        [record(repo_name, pr_number, license_id)],
        [repo],
        markdown=markdown,
        prior_repositories=prior_repositories,
    )


def spdx_known_bundle() -> dict[str, Any]:
    repo = repository(
        "rmems/widget",
        spdx_id="MIT",
        license_name="MIT License",
        url="https://api.github.com/licenses/mit",
    )
    return _single_repo_bundle(
        "rmems/widget",
        "MIT",
        repo,
        1,
        digest=digest_for(repo),
        families=["spdx"],
        unresolved=0,
        markdown=(
            "## License / provenance\n\n"
            "- **Source repository license:** MIT (rmems/widget)\n"
        ),
    )


def license_ref_without_digest_bundle() -> dict[str, Any]:
    identifier = "LicenseRef-TemporalFocus"
    repo = repository(
        "rmems/TemporalFocus.jl",
        spdx_id=identifier,
        license_name="TemporalFocus custom license",
    )
    return _single_repo_bundle("rmems/TemporalFocus.jl", identifier, repo, 7)


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
    return _single_repo_bundle(
        "rmems/TemporalFocus.jl",
        identifier,
        repo,
        7,
        digest=digest_for(repo),
        families=["custom"],
        unresolved=0,
    )


def mismatched_custom_identifier_bundle() -> dict[str, Any]:
    identifier = "LicenseRef-TemporalFocus"
    repo = repository(
        "rmems/TemporalFocus.jl",
        spdx_id=identifier,
        license_name="TemporalFocus custom license",
        custom={
            "identifier": "LicenseRef-Other",
            "name": "Unrelated custom license",
            "text_sha256": CUSTOM_TEXT_SHA256,
        },
    )
    return _single_repo_bundle(
        "rmems/TemporalFocus.jl", identifier, repo, 7, digest=digest_for(repo)
    )


def missing_license_bundle() -> dict[str, Any]:
    repo = repository("rmems/unlicensed", spdx_id=None, license_name=None)
    return _single_repo_bundle("rmems/unlicensed", None, repo, 3)


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
    return _single_repo_bundle(
        "rmems/widget",
        "Apache-2.0",
        current,
        1,
        digest=digest_for(current),
        prior_repositories=[prior],
    )


def stale_digest_bundle() -> dict[str, Any]:
    repo = repository("rmems/widget", spdx_id="MIT", license_name="MIT License")
    return _single_repo_bundle("rmems/widget", "MIT", repo, 1, digest=STALE_DIGEST)


def conflicting_card_manifest_digest_bundle() -> dict[str, Any]:
    repo = repository("rmems/widget", spdx_id="MIT", license_name="MIT License")
    return _bundle(
        card("rmems/widget", "MIT", digest=digest_for(repo)),
        manifest("rmems/widget", "MIT", digest=STALE_DIGEST),
        [record("rmems/widget", 1, "MIT")],
        [repo],
    )


def conflicting_card_manifest_bundle() -> dict[str, Any]:
    repo = repository("rmems/widget", spdx_id="MIT", license_name="MIT License")
    digest = digest_for(repo)
    return _bundle(
        card("rmems/widget", "MIT", digest=digest),
        manifest("rmems/widget", "Apache-2.0", digest=digest),
        [record("rmems/widget", 1, "MIT")],
        [repo],
    )


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
    return _bundle(
        card(repos, licenses, digest=digests),
        manifest(
            repos,
            licenses,
            digest=digests,
            families=["spdx"],
            unresolved=0,
        ),
        [
            record("rmems/widget", 1, "MIT"),
            record("Limen-Neural/axon-encoder", 37, "Apache-2.0"),
        ],
        [mit, apache],
    )


def unknown_license_bundle() -> dict[str, Any]:
    repo = repository("rmems/mystery", spdx_id="NOASSERTION", license_name="Other")
    return _single_repo_bundle("rmems/mystery", "NOASSERTION", repo, 4)


def forge_substitution_bundle() -> dict[str, Any]:
    repo = repository("rmems/unlicensed", spdx_id=None, license_name=None)
    return _single_repo_bundle("rmems/unlicensed", "Apache-2.0", repo, 9)


def apache_source_bundle() -> dict[str, Any]:
    """Source repository is genuinely Apache-2.0; that is not a relicense."""
    repo = repository(
        "rmems/corinth-canal",
        spdx_id="Apache-2.0",
        license_name="Apache License 2.0",
        url="https://api.github.com/licenses/apache-2.0",
    )
    return _single_repo_bundle(
        "rmems/corinth-canal",
        "Apache-2.0",
        repo,
        142,
        digest=digest_for(repo),
        families=["spdx"],
        unresolved=0,
    )


def report_kwargs(bundle: dict[str, Any]) -> dict[str, Any]:
    kwargs = {
        "card": bundle["card"],
        "manifest": bundle["manifest"],
        "markdown_card": bundle["markdown"],
        "prior_repositories": bundle["prior_repositories"],
        "records": bundle["records"],
        "repositories": bundle["repositories"],
        "snapshot_sha256": bundle["snapshot_sha256"],
    }
    if "pull_requests" in bundle:
        kwargs["pull_requests"] = bundle["pull_requests"]
    return kwargs
