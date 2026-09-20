"""Declaration, coverage, and digest reasons for license-closure evaluation."""

from __future__ import annotations

from .license_closure_eval_state import EvalAcc
from .license_closure_ids import _sha256_or_none, normalize_license_id
from .license_closure_inventory import (
    _authenticated_inventory_source_hash,
    _canonical_declared_repos,
    _declaration_map_conflicts,
    _declared_source_maps_conflict,
    _inventory_for_repo,
    _prior_repository,
    declared_digest_for_repo,
    evidence_digest,
    inventory_license_object,
    license_evidence_payload,
)
from .license_closure_pr import (
    _declared_repos,
    _pr_inventory_reasons,
    _source_coverage_invalid,
)


def add_digest_reasons(acc: EvalAcc) -> None:
    if isinstance(acc.repository, dict):
        acc.source_hash = _authenticated_inventory_source_hash(acc.repository)
        acc.digest = evidence_digest(license_evidence_payload(acc.repository))
    acc.card_digest = declared_digest_for_repo(acc.card, acc.names)
    acc.manifest_digest = declared_digest_for_repo(acc.manifest, acc.names)
    acc.declared_digest = acc.card_digest or acc.manifest_digest
    declared_values = {
        item for item in (acc.card_digest, acc.manifest_digest) if item is not None
    }
    if len(declared_values) > 1:
        acc.reasons.append("declarations_disagree")
    if _declaration_map_conflicts(acc.card, acc.manifest, acc.names):
        acc.reasons.append("declarations_disagree")
    _load_prior_digest(acc)


def _load_prior_digest(acc: EvalAcc) -> None:
    if acc.prior_index is None:
        return
    prior_repo = _prior_repository(acc.prior_index, acc.repository, acc.repo)
    if not isinstance(prior_repo, dict):
        return
    if _authenticated_inventory_source_hash(prior_repo) is None:
        acc.reasons.append("source_license_changed")
        return
    acc.prior_id = normalize_license_id(inventory_license_object(prior_repo))
    acc.prior_digest = evidence_digest(license_evidence_payload(prior_repo))


def add_coverage_reasons(acc: EvalAcc) -> None:
    card_repos = _declared_repos(acc.card)
    manifest_repos = _declared_repos(acc.manifest)
    _add_coverage_mismatch_reasons(acc, card_repos, manifest_repos)
    _add_declared_repo_reasons(acc, card_repos, manifest_repos)
    _add_snapshot_reasons(acc)
    acc.reasons.extend(
        _pr_inventory_reasons(
            acc.record, acc.names, acc.pr_number, acc.pull_requests, acc.repository
        )
    )


def _add_coverage_mismatch_reasons(
    acc: EvalAcc, card_repos: set[str], manifest_repos: set[str]
) -> None:
    folded_names = {name.casefold() for name in acc.names}
    if _source_coverage_invalid(acc.card) or _source_coverage_invalid(acc.manifest):
        acc.reasons.append("declarations_disagree")
    if card_repos and not folded_names.intersection(card_repos):
        acc.reasons.append("declarations_disagree")
    if manifest_repos and not folded_names.intersection(manifest_repos):
        acc.reasons.append("declarations_disagree")


def _add_snapshot_reasons(acc: EvalAcc) -> None:
    if not acc.repo or acc.repository is None:
        acc.reasons.append("snapshot_provenance_missing")
    if not _sha256_or_none(acc.snapshot_sha256) or acc.source_hash is None:
        acc.reasons.append("snapshot_provenance_missing")


def _declared_repo_sets_disagree(
    acc: EvalAcc, card_repos: set[str], manifest_repos: set[str]
) -> bool:
    if not card_repos or not manifest_repos:
        return False
    return _canonical_declared_repos(
        card_repos, acc.inventory_index
    ) != _canonical_declared_repos(manifest_repos, acc.inventory_index)


def _add_declared_repo_reasons(
    acc: EvalAcc, card_repos: set[str], manifest_repos: set[str]
) -> None:
    declared_repos = card_repos | manifest_repos
    disagree = (
        _declared_source_maps_conflict(
            acc.card, acc.manifest, declared_repos, acc.inventory_index
        )
        or any(
            _inventory_for_repo(acc.inventory_index, repo) is None
            for repo in declared_repos
        )
        or _declared_repo_sets_disagree(acc, card_repos, manifest_repos)
    )
    if disagree:
        acc.reasons.append("declarations_disagree")
