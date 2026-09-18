"""Offline GitHub page cassette recording and deterministic replay."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

import collect_pr_records as collect_mod
from lib.github_client import GitHubClient, GitHubError
from lib.github_page_fixtures import (
    PAGE_KINDS,
    PageCapture,
    RecordingOpener,
    ReplayOpener,
    ReplayOptions,
    attach_page_recorder,
    build_page_envelope,
    dumps_cassette,
    load_cassette,
    replay_github_client,
    scan_cassette_secrets,
    write_cassette,
)
from lib.normalize import normalize_record
from lib.raw_record import collect_pr
from lib.secrets import find_secrets

ROOT = Path(__file__).resolve().parents[1]
GITHUB_FIXTURES = ROOT / "tests" / "fixtures" / "github"
PAGES_FIXTURES = GITHUB_FIXTURES / "pages"
TRAJECTORY_CASSETTE = PAGES_FIXTURES / "pr89_multipage.json"
JSON_ACCEPT = "application/vnd.github+json"
DIFF_ACCEPT = "application/vnd.github.v3.diff"
API = "https://api.github.com"
REPO = "rmems/corinth-canal"
CARD = ROOT / "datasets" / "cards" / "corinth-canal-v0.json"


class FakeResponse:
    def __init__(self, body: bytes, headers: dict[str, str], url: str, status: int = 200):
        self._body = body
        self.headers = headers
        self.url = url
        self.status = status
        self.code = status

    def read(self, *args: Any, **kwargs: Any) -> bytes:
        del args, kwargs
        return self._body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: Any) -> bool:
        del args
        return False


class ScriptedOpener:
    """In-memory GitHub transport used to prove recording never hits the network."""

    def __init__(self, exchanges: list[tuple[int, dict[str, str], bytes]]):
        self.exchanges = list(exchanges)
        self.requests: list[urllib.request.Request] = []

    def open(self, fullurl, data=None, timeout=None):  # noqa: ANN001
        del data, timeout
        req = fullurl if isinstance(fullurl, urllib.request.Request) else urllib.request.Request(fullurl)
        self.requests.append(req)
        if not self.exchanges:
            raise AssertionError(f"unexpected request {req.full_url}")
        status, headers, body = self.exchanges.pop(0)
        if status >= 400:
            raise urllib.error.HTTPError(
                req.full_url,
                status,
                "scripted error",
                headers,
                _BytesFP(body),
            )
        return FakeResponse(body, headers, req.full_url, status)


class _BytesFP:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self, *args: Any, **kwargs: Any) -> bytes:
        del args, kwargs
        return self._payload


def _headers(**extra: str) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "ETag": 'W/"stable-etag"',
        "X-RateLimit-Limit": "5000",
        "X-RateLimit-Remaining": "4999",
        "X-RateLimit-Reset": "1770000000",
        "X-RateLimit-Resource": "core",
        "Date": "Tue, 15 Sep 2026 00:00:00 GMT",
        "X-GitHub-Request-Id": "ABC123",
        "Server": "github.com",
        "Set-Cookie": "logged_in=no; Path=/; HttpOnly",
    }
    headers.update(extra)
    return headers


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def _envelope(url: str, body: Any, **extras: Any) -> dict[str, Any]:
    if isinstance(body, (bytes, bytearray)):
        raw = bytes(body)
    elif isinstance(body, str):
        raw = body.encode("utf-8")
    else:
        raw = _json_bytes(body)
    return build_page_envelope(
        PageCapture(
            method="GET",
            url=url,
            status=int(extras.get("status", 200)),
            raw_body=raw,
            response_headers=extras.get("headers") or _headers(),
            accept=str(extras.get("accept", JSON_ACCEPT)),
        )
    )


def _load_github(name: str) -> Any:
    path = GITHUB_FIXTURES / name
    if path.suffix == ".diff":
        return path.read_text(encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))


def pr89_multipage_pages() -> list[dict[str, Any]]:
    """PR / issue / comment / review / commit / checks / status / file trajectory."""
    comments = _load_github("issue_comments_89.json")
    extra_comment = {
        "id": 101,
        "user": {"login": "rmems", "type": "User"},
        "body": "Follow-up on page two.",
        "created_at": "2026-05-27T01:10:00Z",
        "author_association": "OWNER",
    }
    comments_p1_link = (
        f"<{API}/repos/{REPO}/issues/89/comments?page=2&per_page=100>; rel=\"next\""
    )
    return [
        _envelope(f"{API}/repos/{REPO}/pulls/89", _load_github("pull_89.json")),
        _envelope(
            f"{API}/repos/{REPO}/issues/89/comments?per_page=100",
            comments,
            headers=_headers(Link=comments_p1_link),
        ),
        _envelope(
            f"{API}/repos/{REPO}/issues/89/comments?page=2&per_page=100",
            [extra_comment],
        ),
        _envelope(
            f"{API}/repos/{REPO}/pulls/89/comments?per_page=100",
            _load_github("review_comments_89.json"),
        ),
        _envelope(
            f"{API}/repos/{REPO}/pulls/89/reviews?per_page=100",
            _load_github("reviews_89.json"),
        ),
        _envelope(
            f"{API}/repos/{REPO}/pulls/89/commits?per_page=100",
            _load_github("commits_89.json"),
        ),
        _envelope(
            f"{API}/repos/{REPO}/pulls/89/files?per_page=100",
            _load_github("files_89.json"),
        ),
        _envelope(
            f"{API}/repos/{REPO}/pulls/89",
            _load_github("diff_89.diff"),
            headers=_headers(**{"Content-Type": "text/plain; charset=utf-8"}),
            accept=DIFF_ACCEPT,
        ),
        _envelope(
            f"{API}/repos/{REPO}/commits/def/check-runs?per_page=100",
            _load_github("check_runs_89.json"),
        ),
        _envelope(
            f"{API}/repos/{REPO}/commits/def/status",
            _load_github("status_89.json"),
        ),
        _envelope(
            f"{API}/repos/{REPO}/issues/74",
            _load_github("issue_74.json"),
        ),
    ]


def test_sanitize_strips_credentials_unstable_headers_and_home_paths():
    token = "ghp_" + ("A" * 36)
    raw_headers = _headers(
        **{
            "Authorization": f"Bearer {token}",
            "Cookie": "user=raulmc; session=abc",
            "Link": (
                f"<{API}/repos/{REPO}/issues/89/comments"
                f"?access_token={token}&page=2>; rel=\"next\""
            ),
        }
    )
    body = {
        "body": f"token={token} path=/home/raulmc/.config/gh/hosts.yml",
        "url": f"{API}/repos/{REPO}/issues/89/comments?token={token}",
    }
    page = build_page_envelope(
        PageCapture(
            method="GET",
            url=f"https://user:{token}@api.github.com/repos/{REPO}/issues/89/comments?access_token={token}&page=1",
            status=200,
            raw_body=_json_bytes(body),
            response_headers=raw_headers,
        )
    )
    dumped = dumps_cassette([page])
    assert token not in dumped
    assert "authorization" not in dumped.lower()
    assert "set-cookie" not in dumped.lower()
    assert "logged_in" not in dumped
    assert "/home/raulmc" not in dumped
    assert "x-github-request-id" not in dumped.lower()
    assert '"date"' not in dumped.lower()
    assert page["pagination"]["next"]
    assert "access_token" not in (page["pagination"]["next"] or "")
    assert page["etag"] == 'W/"stable-etag"'
    assert page["rate_limit"]["remaining"] == 4999
    assert page["identity"]["etag"] == page["etag"]
    assert scan_cassette_secrets({"pages": [page]}) == []


def test_fixture_normalization_is_deterministic(tmp_path: Path):
    pages = pr89_multipage_pages()
    first = dumps_cassette(pages)
    second = dumps_cassette(pages)
    assert first == second
    path = tmp_path / "cassette.json"
    write_cassette(path, pages)
    loaded = load_cassette(path)
    assert dumps_cassette(loaded["pages"]) == first
    committed = TRAJECTORY_CASSETTE.read_text(encoding="utf-8")
    assert committed == first


def test_replay_collects_multipage_trajectory_without_network():
    client = replay_github_client(TRAJECTORY_CASSETTE)
    record = collect_pr(client, REPO, 89)
    assert record["source"]["pr_number"] == 89
    assert len(record["issue_comments"]) == 2
    assert record["issue_comments"][1]["body"] == "Follow-up on page two."
    assert record["linked_issues"][0]["number"] == 74
    assert record["files"]
    assert record["diff"]["inline"]
    kinds = [page["kind"] for page in load_cassette(TRAJECTORY_CASSETTE)["pages"]]
    assert set(kinds) <= set(PAGE_KINDS)
    assert kinds == [
        "pull",
        "comment",
        "comment",
        "comment",
        "review",
        "commit",
        "file",
        "diff",
        "checks",
        "status",
        "issue",
    ]
    card = json.loads(CARD.read_text(encoding="utf-8")) if CARD.exists() else {}
    traj = normalize_record(record, card)
    assert traj["id"] == "rmems-corinth-canal-89"
    assert traj["outcome"] == "merged"


def test_replay_rate_limit_403_then_success():
    url = f"{API}/repos/{REPO}/pulls/89"
    pages = [
        _envelope(
            url,
            {"message": "API rate limit exceeded"},
            status=403,
            headers=_headers(
                **{
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": "0",
                    "X-RateLimit-Reset": "1",
                }
            ),
        ),
        _envelope(url, _load_github("pull_89.json")),
    ]
    slept: list[float] = []
    client = replay_github_client(pages, ReplayOptions(sleep_fn=slept.append))
    payload = client.get_json(f"/repos/{REPO}/pulls/89")
    assert payload["merged"] is True
    assert slept


def test_replay_terminal_404():
    url = f"{API}/repos/{REPO}/issues/404"
    pages = [
        _envelope(url, {"message": "Not Found"}, status=404, headers=_headers(**{"X-RateLimit-Remaining": "10"}))
    ]
    client = replay_github_client(pages, ReplayOptions(max_retries=0))
    with pytest.raises(GitHubError, match="404") as excinfo:
        client.get_json(f"/repos/{REPO}/issues/404")
    assert excinfo.value.status == 404


def test_replay_malformed_json():
    url = f"{API}/repos/{REPO}/pulls/89"
    pages = [_envelope(url, "{not json", headers=_headers())]
    assert pages[0]["malformed_json"] is True
    client = replay_github_client(pages)
    with pytest.raises(json.JSONDecodeError):
        client.get_json(f"/repos/{REPO}/pulls/89")


def test_replay_truncated_check_runs():
    url = f"{API}/repos/{REPO}/commits/def/check-runs?per_page=100"
    body = {
        "total_count": 5,
        "check_runs": [
            {
                "name": "CUDA Build",
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://github.com/rmems/corinth-canal/actions",
            }
        ],
    }
    pages = [
        _envelope(f"{API}/repos/{REPO}/pulls/89", _load_github("pull_89.json")),
        _envelope(f"{API}/repos/{REPO}/issues/89/comments?per_page=100", []),
        _envelope(f"{API}/repos/{REPO}/pulls/89/comments?per_page=100", []),
        _envelope(f"{API}/repos/{REPO}/pulls/89/reviews?per_page=100", []),
        _envelope(f"{API}/repos/{REPO}/pulls/89/commits?per_page=100", []),
        _envelope(f"{API}/repos/{REPO}/pulls/89/files?per_page=100", []),
        _envelope(
            f"{API}/repos/{REPO}/pulls/89",
            _load_github("diff_89.diff"),
            headers=_headers(**{"Content-Type": "text/plain; charset=utf-8"}),
            accept=DIFF_ACCEPT,
        ),
        _envelope(url, body),
        _envelope(f"{API}/repos/{REPO}/commits/def/status", _load_github("status_89.json")),
    ]
    assert pages[7]["truncated"] is True
    client = replay_github_client(pages)
    record = collect_pr(client, REPO, 89)
    assert any(w.startswith("check_runs_truncated") for w in record["collection_meta"]["warnings"])


def test_replay_duplicate_comment_pages():
    url = f"{API}/repos/{REPO}/issues/89/comments?per_page=100"
    comment = _load_github("issue_comments_89.json")
    link = f"<{url}>; rel=\"next\""
    pages = [
        _envelope(url, comment, headers=_headers(Link=link)),
        _envelope(url, comment),
    ]
    assert pages[1]["duplicate"] is False  # mark_duplicates runs on cassette dump
    dumped = json.loads(dumps_cassette(pages))
    assert dumped["pages"][1]["duplicate"] is True
    assert dumped["pages"][1]["duplicate_of"] == 0
    client = replay_github_client(dumped)
    items = client.get_all(f"/repos/{REPO}/issues/89/comments")
    assert len(items) == 2
    assert items[0]["id"] == items[1]["id"]


def test_replay_changed_etag():
    url = f"{API}/repos/{REPO}/pulls/89"
    first = _envelope(url, {"n": 1}, headers=_headers(ETag='W/"one"'))
    second = _envelope(url, {"n": 2}, headers=_headers(ETag='W/"two"'))
    assert first["etag"] != second["etag"]
    assert first["identity"]["body_sha256"] != second["identity"]["body_sha256"]
    client = replay_github_client([first, second])
    data1, headers1 = client.get_json_with_headers(f"/repos/{REPO}/pulls/89")
    data2, headers2 = client.get_json_with_headers(f"/repos/{REPO}/pulls/89")
    assert data1 == {"n": 1}
    assert data2 == {"n": 2}
    assert headers1["etag"] == 'W/"one"'
    assert headers2["etag"] == 'W/"two"'


def test_secret_scanner_over_recorded_fixtures():
    leaks: list[str] = []
    for path in sorted(PAGES_FIXTURES.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        hits = scan_cassette_secrets(text)
        assert hits == [], f"{path} leaked {hits}"
        leaks.extend(find_secrets(text))
        lowered = text.lower()
        assert "authorization" not in lowered
        assert "ghp_" not in lowered
        assert "/home/" not in text
        assert "/Users/" not in text
        assert "c:\\users\\" not in lowered
    assert leaks == []


def test_record_then_replay_roundtrip_is_ordered_and_get_only():
    url = f"{API}/repos/{REPO}/pulls/89"
    live = ScriptedOpener(
        [
            (
                200,
                _headers(Authorization="Bearer ghp_" + ("B" * 36)),
                _json_bytes(_load_github("pull_89.json")),
            )
        ]
    )
    client = GitHubClient(
        token="ghp_" + ("C" * 36),
        opener=RecordingOpener(live),
        sleep_fn=lambda _s: None,
    )
    recorder = client._opener
    assert isinstance(recorder, RecordingOpener)
    payload = client.get_json(f"/repos/{REPO}/pulls/89")
    assert payload["title"]
    dumped = dumps_cassette(recorder.pages)
    assert live.requests and live.requests[0].has_header("Authorization")
    assert "ghp_" not in dumped
    assert "authorization" not in dumped.lower()
    assert recorder.pages[0]["kind"] == "pull"
    replayed = replay_github_client(recorder.pages).get_json(f"/repos/{REPO}/pulls/89")
    assert replayed["title"] == payload["title"]
    with pytest.raises(GitHubError, match="non-GET"):
        ReplayOpener(recorder.pages).open(
            urllib.request.Request(url, data=b"{}", method="POST")
        )


def test_attach_page_recorder_keeps_existing_client_read_only():
    live = ScriptedOpener(
        [
            (200, _headers(), _json_bytes({"ok": True})),
        ]
    )
    client = GitHubClient(token=None, opener=live, sleep_fn=lambda _s: None)
    recorder = attach_page_recorder(client)
    assert client.get_json(f"{API}/repos/{REPO}/pulls/1") == {"ok": True}
    assert recorder.pages[0]["method"] == "GET"
    post = urllib.request.Request(f"{API}/graphql", data=b"{}", method="POST")
    with pytest.raises(GitHubError, match="non-GET"):
        client._opener.open(post)


def test_collect_pr_records_writes_sanitized_cassette(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cassette_path = tmp_path / "recorded.json"
    out_dir = tmp_path / "raw"
    monkeypatch.setattr(
        collect_mod.GitHubClient,
        "from_env",
        classmethod(lambda cls, env_name="GITHUB_TOKEN": replay_github_client(TRAJECTORY_CASSETTE)),
    )
    rc = collect_mod.main(
        [
            "--repo",
            REPO,
            "--pr",
            "89",
            "--out-dir",
            str(out_dir),
            "--record-pages",
            str(cassette_path),
        ]
    )
    assert rc == 0
    assert (out_dir / "pr-89.json").exists()
    recorded = load_cassette(cassette_path)
    assert recorded["page_count"] == 11
    assert scan_cassette_secrets(recorded) == []
    assert dumps_cassette(recorded["pages"]) == TRAJECTORY_CASSETTE.read_text(encoding="utf-8")


def test_paginated_check_runs_are_not_truncated():
    url = f"{API}/repos/{REPO}/commits/def/check-runs?per_page=100"
    link = f"<{url}&page=2>; rel=\"next\""
    body = {
        "total_count": 5,
        "check_runs": [
            {
                "name": "CUDA Build",
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://github.com/rmems/corinth-canal/actions",
            }
        ],
    }
    page = _envelope(url, body, headers=_headers(Link=link))
    assert page["truncated"] is False
    assert page["pagination"]["next"]


def test_load_cassette_rejects_mismatched_page_count(tmp_path: Path):
    path = tmp_path / "bad.json"
    payload = json.loads(dumps_cassette(pr89_multipage_pages()[:1]))
    payload["page_count"] = 99
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(GitHubError, match="page_count"):
        load_cassette(path)


def test_load_cassette_rejects_wrong_schema_version(tmp_path: Path):
    path = tmp_path / "bad.json"
    payload = json.loads(dumps_cassette(pr89_multipage_pages()[:1]))
    payload["schema_version"] = "github_page_cassette_v0"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(GitHubError, match="schema_version"):
        load_cassette(path)


def test_recording_uses_request_url_not_redirect_target():
    requested = f"{API}/repos/old-owner/old-name/pulls/89"
    final = f"{API}/repos/{REPO}/pulls/89"

    class RedirectOpener:
        def open(self, fullurl, data=None, timeout=None):  # noqa: ANN001
            del data, timeout
            req = fullurl if isinstance(fullurl, urllib.request.Request) else urllib.request.Request(fullurl)
            return FakeResponse(_json_bytes(_load_github("pull_89.json")), _headers(), final, 200)

    recorder = RecordingOpener(RedirectOpener())
    client = GitHubClient(token="x", opener=recorder, sleep_fn=lambda _s: None)
    payload = client.get_json(requested)
    assert payload["merged"] is True
    assert recorder.pages[0]["url"] == requested
    replayed = replay_github_client(recorder.pages).get_json(requested)
    assert replayed["merged"] is True


def test_recording_returns_raw_body_to_collector():
    token = "ghp_" + ("D" * 36)
    live = ScriptedOpener(
        [(200, _headers(), _json_bytes({"body": token, "path": "/home/raulmc/secret"}))]
    )
    recorder = RecordingOpener(live)
    client = GitHubClient(token="x", opener=recorder, sleep_fn=lambda _s: None)
    payload = client.get_json(f"{API}/repos/{REPO}/pulls/89")
    assert payload["body"] == token
    assert payload["path"] == "/home/raulmc/secret"
    dumped = dumps_cassette(recorder.pages)
    assert token not in dumped
    assert "/home/raulmc" not in dumped


class _FalseyOpener:
    def __bool__(self) -> bool:
        return False

    def open(self, fullurl, data=None, timeout=None):  # noqa: ANN001
        del data, timeout
        req = fullurl if isinstance(fullurl, urllib.request.Request) else urllib.request.Request(fullurl)
        return FakeResponse(_json_bytes({"ok": True}), _headers(), req.full_url, 200)


def test_falsey_custom_opener_is_kept():
    opener = _FalseyOpener()
    client = GitHubClient(token="x", opener=opener, sleep_fn=lambda _s: None)
    assert client._opener is opener
    assert client.get_json(f"{API}/repos/{REPO}/pulls/1") == {"ok": True}


def test_cassette_write_failure_returns_collector_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def boom(path: Path, pages: list[dict[str, Any]]) -> Path:
        del path, pages
        raise OSError("disk full")

    monkeypatch.setattr(collect_mod, "write_cassette", boom)
    monkeypatch.setattr(
        collect_mod.GitHubClient,
        "from_env",
        classmethod(lambda cls, env_name="GITHUB_TOKEN": replay_github_client(TRAJECTORY_CASSETTE)),
    )
    rc = collect_mod.main(
        [
            "--repo",
            REPO,
            "--pr",
            "89",
            "--out-dir",
            str(tmp_path / "raw"),
            "--record-pages",
            str(tmp_path / "out.json"),
        ]
    )
    assert rc == 1
