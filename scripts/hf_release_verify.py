#!/usr/bin/env python3
"""Release-environment Hugging Face publish verification.

Never runs on pull requests. PRs must not receive HF_TOKEN. This script
verifies local JSONL/Parquet checksums, a resumable upload plan, metadata,
pinned-revision download, and refuses to overwrite an immutable tag.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.ci_contracts import (  # noqa: E402
    JSONL_DIR,
    PARQUET_DIR,
    RELEASE_MANIFEST,
    load_jsonl,
    sha256_file,
)

try:
    from huggingface_hub import HfApi, hf_hub_download
except ImportError:
    HfApi = None
    hf_hub_download = None

DEFAULT_REPO = "rmems/operation-prometheus-trajectories"
IMMUTABLE_TAG_RE = r"^v\\d+\\.\\d+\\.\\d+$"
RELEASE_EVENT_ENV = "GITHUB_EVENT_NAME"


class ReleaseVerifyError(ValueError):
    """A release-verify precondition failed."""


def _event_name() -> str:
    return os.environ.get(RELEASE_EVENT_ENV, "").strip()


def refuse_pull_request_context() -> None:
    if _event_name() == "pull_request":
        raise ReleaseVerifyError(
            "hf-release-verify must not run on pull_request events"
        )
    if os.environ.get("GITHUB_EVENT_NAME") == "pull_request":
        raise ReleaseVerifyError(
            "hf-release-verify must not run on pull_request events"
        )


def jsonl_outputs(jsonl_dir: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(jsonl_dir.glob("*.jsonl")):
        rows = load_jsonl(path)
        files.append(
            {
                "path": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "record_count": len(rows),
            }
        )
    return files


def parquet_outputs(parquet_dir: Path) -> list[dict[str, Any]]:
    if not parquet_dir.is_dir():
        return []
    files: list[dict[str, Any]] = []
    for path in sorted(parquet_dir.glob("*.parquet")):
        files.append(
            {
                "path": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    return files


def build_release_manifest(
    jsonl_dir: Path,
    parquet_dir: Path,
    *,
    tag: str,
    dataset_repo: str,
) -> dict[str, Any]:
    jsonl = jsonl_outputs(jsonl_dir)
    parquet = parquet_outputs(parquet_dir)
    payload = {
        "schema_version": "prometheus.release-manifest.v1",
        "dataset_repo": dataset_repo,
        "tag": tag,
        "jsonl": jsonl,
        "parquet": parquet,
        "configs": ["datasets/cards", "schemas"],
    }
    payload["sha256"] = hashlib.sha256(
        json.dumps(
            {key: value for key, value in payload.items() if key != "sha256"},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    return payload


def resumable_upload_plan(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Describe a resumable upload. Each file is addressed by sha256 so a retry
    resumes from the blob identity rather than overwriting an immutable tag.
    """
    return [
        {
            "path": item["path"],
            "sha256": item["sha256"],
            "bytes": item["bytes"],
            "resume_key": f"sha256:{item['sha256']}",
        }
        for item in files
    ]


def refuse_overwrite_immutable_tag(
    tag: str,
    local_sha256: str,
    remote_tags: dict[str, str],
) -> None:
    if not re.fullmatch(IMMUTABLE_TAG_RE, tag):
        raise ReleaseVerifyError(
            f"Refusing non-immutable tag {tag!r}; expected vMAJOR.MINOR.PATCH"
        )
    remote = remote_tags.get(tag)
    if remote is None:
        return
    if remote != local_sha256:
        raise ReleaseVerifyError(
            f"Refusing to overwrite immutable tag {tag}: remote {remote} != local {local_sha256}"
        )


def pinned_revision_checksums(
    downloaded: dict[str, str],
    expected: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    for item in expected:
        actual = downloaded.get(item["path"])
        if actual is None:
            errors.append(f"pinned revision is missing {item['path']}")
        elif actual != item["sha256"]:
            errors.append(f"pinned revision checksum mismatch for {item['path']}")
    return errors


def _tag_name_and_oid(tag: Any) -> tuple[str, str] | None:
    name = getattr(tag, "name", None) or getattr(tag, "ref", None)
    oid = getattr(tag, "target_commit", None) or getattr(tag, "ref", None)
    if name and oid:
        return str(name), str(oid)
    return None


def load_remote_tags(dataset_repo: str, token: str | None) -> dict[str, str]:
    if not token:
        return {}
    if HfApi is None:
        raise ReleaseVerifyError("huggingface_hub is required when HF_TOKEN is set")
    refs = HfApi(token=token).list_repo_refs(dataset_repo, repo_type="dataset")
    tags: dict[str, str] = {}
    for tag in getattr(refs, "tags", []) or []:
        parsed = _tag_name_and_oid(tag)
        if parsed is not None:
            tags[parsed[0]] = parsed[1]
    return tags


def download_pinned_checksums(
    dataset_repo: str,
    revision: str,
    filenames: list[str],
    token: str | None,
) -> dict[str, str]:
    if not token:
        return {}
    if hf_hub_download is None:
        raise ReleaseVerifyError("huggingface_hub is required when HF_TOKEN is set")
    checksums: dict[str, str] = {}
    for name in filenames:
        local = hf_hub_download(
            repo_id=dataset_repo,
            filename=name,
            repo_type="dataset",
            revision=revision,
            token=token,
        )
        checksums[name] = sha256_file(Path(local))
    return checksums


def _require_local_outputs(manifest: dict[str, Any], parquet_dir: Path) -> None:
    if not manifest["jsonl"]:
        raise ReleaseVerifyError("release is missing JSONL outputs")
    if parquet_dir.is_dir() and not any(parquet_dir.glob("*.parquet")):
        raise ReleaseVerifyError(
            "parquet directory exists but contains no Parquet outputs"
        )


def _pinned_checksum_errors(
    *,
    tag: str,
    dataset_repo: str,
    artifacts: list[dict[str, Any]],
    tags: dict[str, str],
    downloaded: dict[str, str] | None,
) -> list[str]:
    resolved = downloaded
    if resolved is None and os.environ.get("HF_TOKEN") and tag in tags:
        resolved = download_pinned_checksums(
            dataset_repo,
            tag,
            [item["path"] for item in artifacts],
            os.environ.get("HF_TOKEN"),
        )
    if not resolved:
        return []
    return pinned_revision_checksums(resolved, artifacts)


def verify(
    *,
    tag: str,
    dataset_repo: str,
    jsonl_dir: Path,
    parquet_dir: Path,
    remote_tags: dict[str, str] | None = None,
    downloaded: dict[str, str] | None = None,
) -> dict[str, Any]:
    refuse_pull_request_context()
    if os.environ.get("HF_TOKEN") and _event_name() == "pull_request":
        raise ReleaseVerifyError("PRs must never receive HF_TOKEN")
    manifest = build_release_manifest(
        jsonl_dir, parquet_dir, tag=tag, dataset_repo=dataset_repo
    )
    _require_local_outputs(manifest, parquet_dir)
    artifacts = manifest["jsonl"] + manifest["parquet"]
    plan = resumable_upload_plan(artifacts)
    tags = (
        remote_tags
        if remote_tags is not None
        else load_remote_tags(dataset_repo, os.environ.get("HF_TOKEN"))
    )
    refuse_overwrite_immutable_tag(tag, manifest["sha256"], tags)
    checksum_errors = _pinned_checksum_errors(
        tag=tag,
        dataset_repo=dataset_repo,
        artifacts=artifacts,
        tags=tags,
        downloaded=downloaded,
    )
    if checksum_errors:
        raise ReleaseVerifyError("; ".join(checksum_errors))
    return {
        "ok": True,
        "tag": tag,
        "dataset_repo": dataset_repo,
        "release_manifest": manifest,
        "upload_plan": plan,
        "wrote_local_manifest": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="v0.7.0")
    parser.add_argument("--dataset-repo", default=DEFAULT_REPO)
    parser.add_argument("--jsonl-dir", type=Path, default=JSONL_DIR)
    parser.add_argument("--parquet-dir", type=Path, default=PARQUET_DIR)
    parser.add_argument(
        "--out", type=Path, default=Path("reports/hf-release-verify.json")
    )
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="Write datasets/release/manifest.json from the verified local outputs",
    )
    args = parser.parse_args(argv)
    try:
        result = verify(
            tag=args.tag,
            dataset_repo=args.dataset_repo,
            jsonl_dir=args.jsonl_dir,
            parquet_dir=args.parquet_dir,
        )
    except ReleaseVerifyError as exc:
        print(f"hf-release-verify FAILED: {exc}", file=sys.stderr)
        return 1
    if args.write_manifest:
        RELEASE_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        RELEASE_MANIFEST.write_text(
            json.dumps(result["release_manifest"], indent=2, ensure_ascii=False) + "\\n",
            encoding="utf-8",
        )
        result["wrote_local_manifest"] = True
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\\n", encoding="utf-8"
    )
    print(f"hf-release-verify passed for {args.dataset_repo}@{args.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
