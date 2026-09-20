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


def repository(name: str, **spec: Any) -> dict[str, Any]:
    spdx_id = spec.get("spdx_id")
    row: dict[str, Any] = {
        "name_with_owner": name,
        "license": {
            "spdx_id": spdx_id,
            "name": spec.get("license_name") or spdx_id,
            "url": spec.get("url"),
        },
        "visibility": "public",
    }
    if spec.get("custom") is not None:
        row["custom_license"] = spec["custom"]
    row["source_hash"] = spec.get("source_hash") or inventory_row_source_hash(row)
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


def record(repo: str, pr_number: int, license_id: str | None, **spec) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": spec.get("record_id") or f"{repo.replace('/', '-')}-{pr_number}",
        "repo": repo,
        "pr_number": pr_number,
        "source_urls": [f"https://github.com/{repo}/pull/{pr_number}"],
    }
    if license_id is not None:
        row["license"] = license_id
    return row


def with_code_state(row: dict[str, Any], **oids: str) -> dict[str, Any]:
    updated = dict(row)
    updated["repository"] = {
        "base_oid": oids.get("base_oid", BASE_OID),
        "head_oid": oids.get("head_oid", HEAD_OID),
        "commit_oid": oids.get("commit_oid", MERGE_OID),
    }
    return updated


def inventory_pr(repo: str, number: int, **oids: str) -> dict[str, Any]:
    return bind_pr_source_hash(
        {
            "base_oid": oids.get("base_oid", BASE_OID),
            "head_oid": oids.get("head_oid", HEAD_OID),
            "merge_commit_oid": oids.get("merge_commit_oid", MERGE_OID),
            "number": number,
            "repository_name_with_owner": repo,
        }
    )


def card(
    repo: str | list[str], license_id: str | dict[str, str] | None, **extra: Any
) -> dict[str, Any]:
    digest = extra.get("digest")
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
    repo: str | list[str], license_id: str | dict[str, str] | None, **extra: Any
) -> dict[str, Any]:
    payload = card(repo, license_id, digest=extra.get("digest"))
    if extra.get("families") is not None:
        payload["license_families"] = extra["families"]
    if extra.get("unresolved") is not None:
        payload["unresolved_license_count"] = extra["unresolved"]
    return payload


def digest_for(repo_row: dict[str, Any]) -> str:
    return evidence_digest(license_evidence_payload(repo_row))


def _bundle(
    docs: tuple[dict[str, Any], dict[str, Any]],
    records: list[dict[str, Any]],
    repositories: list[dict[str, Any]],
    **extra: Any,
) -> dict[str, Any]:
    card_payload, manifest_payload = docs
    return {
        "card": card_payload,
        "manifest": manifest_payload,
        "markdown": extra.get("markdown"),
        "prior_repositories": extra.get("prior_repositories"),
        "records": records,
        "repositories": repositories,
        "snapshot_sha256": SNAPSHOT_SHA256,
    }


def _single_repo_bundle(
    repo_name: str,
    license_id: str | None,
    repo: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any]:
    digest = spec.get("digest")
    return _bundle(
        (
            card(repo_name, license_id, digest=digest),
            manifest(
                repo_name,
                license_id,
                digest=digest,
                families=spec.get("families"),
                unresolved=spec.get("unresolved"),
            ),
        ),
        [record(repo_name, spec["pr_number"], license_id)],
        [repo],
        markdown=spec.get("markdown"),
        prior_repositories=spec.get("prior_repositories"),
    )


def _repo_bundle(
    repo_name: str,
    license_id: str | None,
    repo_spec: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any]:
    repo = repository(repo_name, **repo_spec)
    return _single_repo_bundle(repo_name, license_id, repo, spec)


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
        {
            "pr_number": 1,
            "digest": digest_for(repo),
            "families": ["spdx"],
            "unresolved": 0,
            "markdown": (
                "## License / provenance\n\n"
                "- **Source repository license:** MIT (rmems/widget)\n"
            ),
        },
    )


def license_ref_without_digest_bundle() -> dict[str, Any]:
    identifier = "LicenseRef-TemporalFocus"
    return _repo_bundle(
        "rmems/TemporalFocus.jl",
        identifier,
        {"spdx_id": identifier, "license_name": "TemporalFocus custom license"},
        {"pr_number": 7},
    )


def custom_license_bundle() -> dict[str, Any]:
    identifier = "LicenseRef-TemporalFocus"
    repo_spec = {
        "spdx_id": identifier,
        "license_name": "TemporalFocus custom license",
        "custom": {
            "identifier": identifier,
            "name": "TemporalFocus custom license",
            "text_sha256": CUSTOM_TEXT_SHA256,
        },
    }
    repo = repository("rmems/TemporalFocus.jl", **repo_spec)
    return _single_repo_bundle(
        "rmems/TemporalFocus.jl",
        identifier,
        repo,
        {
            "pr_number": 7,
            "digest": digest_for(repo),
            "families": ["custom"],
            "unresolved": 0,
        },
    )


def mismatched_custom_identifier_bundle() -> dict[str, Any]:
    repo = repository(
        "rmems/TemporalFocus.jl",
        spdx_id="LicenseRef-TemporalFocus",
        license_name="TemporalFocus custom license",
        custom={
            "identifier": "LicenseRef-Other",
            "name": "Unrelated custom license",
            "text_sha256": CUSTOM_TEXT_SHA256,
        },
    )
    return _single_repo_bundle(
        "rmems/TemporalFocus.jl",
        "LicenseRef-TemporalFocus",
        repo,
        {"pr_number": 7, "digest": digest_for(repo)},
    )


def missing_license_bundle() -> dict[str, Any]:
    return _repo_bundle(
        "rmems/unlicensed", None, {"spdx_id": None}, {"pr_number": 3}
    )


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
        {
            "pr_number": 1,
            "digest": digest_for(current),
            "prior_repositories": [prior],
        },
    )


def stale_digest_bundle() -> dict[str, Any]:
    repo = repository("rmems/widget", spdx_id="MIT", license_name="MIT License")
    return _single_repo_bundle(
        "rmems/widget",
        "MIT",
        repo,
        {"pr_number": 1, "digest": STALE_DIGEST},
    )


def conflicting_card_manifest_digest_bundle() -> dict[str, Any]:
    repo = repository("rmems/widget", spdx_id="MIT", license_name="MIT License")
    return _bundle(
        (
            card("rmems/widget", "MIT", digest=digest_for(repo)),
            manifest("rmems/widget", "MIT", digest=STALE_DIGEST),
        ),
        [record("rmems/widget", 1, "MIT")],
        [repo],
    )


def conflicting_card_manifest_bundle() -> dict[str, Any]:
    repo = repository("rmems/widget", spdx_id="MIT", license_name="MIT License")
    digest = digest_for(repo)
    return _bundle(
        (
            card("rmems/widget", "MIT", digest=digest),
            manifest("rmems/widget", "Apache-2.0", digest=digest),
        ),
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
        (
            card(repos, licenses, digest=digests),
            manifest(
                repos,
                licenses,
                digest=digests,
                families=["spdx"],
                unresolved=0,
            ),
        ),
        [
            record("rmems/widget", 1, "MIT"),
            record("Limen-Neural/axon-encoder", 37, "Apache-2.0"),
        ],
        [mit, apache],
    )


def unknown_license_bundle() -> dict[str, Any]:
    return _repo_bundle(
        "rmems/mystery",
        "NOASSERTION",
        {"spdx_id": "NOASSERTION", "license_name": "Other"},
        {"pr_number": 4},
    )


def forge_substitution_bundle() -> dict[str, Any]:
    return _repo_bundle(
        "rmems/unlicensed", "Apache-2.0", {"spdx_id": None}, {"pr_number": 9}
    )


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
        {
            "pr_number": 142,
            "digest": digest_for(repo),
            "families": ["spdx"],
            "unresolved": 0,
        },
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
