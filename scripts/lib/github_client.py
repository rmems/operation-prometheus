"""Rate-limit-aware read-only GitHub REST client (stdlib only)."""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from typing import Any

logger = logging.getLogger(__name__)

API_VERSION = "2022-11-28"
USER_AGENT = (
    "operation-prometheus-collector/0.1 "
    "(+https://github.com/rmems/operation-prometheus; Grok Build Agent: Grok 4.5)"
)
DEFAULT_BASE = "https://api.github.com"


class GitHubError(RuntimeError):
    """Raised for non-retryable GitHub API failures."""

    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


class GitHubClient:
    """Minimal GET-only GitHub REST client with rate-limit awareness."""

    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str = DEFAULT_BASE,
        max_retries: int = 5,
        min_remaining: int = 2,
        sleep_fn=time.sleep,
    ) -> None:
        self.token = token if token else None
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.min_remaining = min_remaining
        self._sleep = sleep_fn
        if not self.token:
            logger.warning(
                "No GitHub token configured; unauthenticated rate limit is ~60 req/hr"
            )

    @classmethod
    def from_env(cls, env_name: str = "GITHUB_TOKEN") -> GitHubClient:
        return cls(token=os.environ.get(env_name) or None)

    def _headers(self, accept: str = "application/vnd.github+json") -> dict[str, str]:
        headers = {
            "Accept": accept,
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": API_VERSION,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _resolve_url(self, path_or_url: str) -> str:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url
        if not path_or_url.startswith("/"):
            path_or_url = "/" + path_or_url
        return self.base_url + path_or_url

    def _request(
        self,
        path_or_url: str,
        *,
        accept: str = "application/vnd.github+json",
    ) -> tuple[bytes, dict[str, str]]:
        url = self._resolve_url(path_or_url)
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(url, headers=self._headers(accept), method="GET")
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    body = resp.read()
                    headers = {k.lower(): v for k, v in resp.headers.items()}
                    self._maybe_throttle(headers)
                    return body, headers
            except urllib.error.HTTPError as exc:
                last_err = exc
                status = exc.code
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                if status in (403, 429, 500, 502, 503, 504) and attempt < self.max_retries:
                    delay = self._backoff_seconds(attempt, retry_after, exc)
                    logger.warning(
                        "GitHub %s on %s; retry %s/%s after %.1fs",
                        status,
                        url,
                        attempt + 1,
                        self.max_retries,
                        delay,
                    )
                    self._sleep(delay)
                    continue
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                raise GitHubError(
                    f"GET {url} failed with {status}: {detail}",
                    status=status,
                ) from exc
            except urllib.error.URLError as exc:
                last_err = exc
                if attempt < self.max_retries:
                    delay = min(60.0, 2.0**attempt)
                    logger.warning("Network error on %s: %s; retry after %.1fs", url, exc, delay)
                    self._sleep(delay)
                    continue
                raise GitHubError(f"GET {url} network error: {exc}") from exc
        raise GitHubError(f"GET {url} failed after retries: {last_err}")

    def _backoff_seconds(
        self,
        attempt: int,
        retry_after: str | None,
        exc: urllib.error.HTTPError,
    ) -> float:
        if retry_after:
            try:
                return float(retry_after) + 0.5
            except ValueError:
                pass
        # Secondary rate limit hint
        try:
            body = exc.read()
            text = body.decode("utf-8", errors="replace").lower()
            if "secondary rate limit" in text:
                return 60.0
        except Exception:
            pass
        reset = exc.headers.get("X-RateLimit-Reset") if exc.headers else None
        if reset:
            try:
                wait = max(0.0, float(reset) - time.time()) + 1.0
                return min(wait, 120.0)
            except ValueError:
                pass
        return min(60.0, 2.0**attempt)

    def _maybe_throttle(self, headers: dict[str, str]) -> None:
        remaining = headers.get("x-ratelimit-remaining")
        reset = headers.get("x-ratelimit-reset")
        if remaining is None:
            return
        try:
            rem = int(remaining)
        except ValueError:
            return
        if rem > self.min_remaining:
            return
        if not reset:
            self._sleep(5.0)
            return
        try:
            wait = max(0.0, float(reset) - time.time()) + 1.0
        except ValueError:
            wait = 5.0
        logger.info("Rate limit low (remaining=%s); sleeping %.1fs", rem, wait)
        self._sleep(min(wait, 120.0))

    def get_json(self, path_or_url: str) -> Any:
        body, _ = self._request(path_or_url)
        if not body:
            return None
        return json.loads(body.decode("utf-8"))

    def get_text(
        self,
        path_or_url: str,
        *,
        accept: str = "application/vnd.github.v3.diff",
    ) -> str:
        body, _ = self._request(path_or_url, accept=accept)
        return body.decode("utf-8", errors="replace")

    def paginate(self, path: str, *, per_page: int = 100) -> Iterator[list[Any]]:
        """Yield pages of list results, following Link rel=next."""
        if "?" in path:
            url = f"{path}&per_page={per_page}"
        else:
            url = f"{path}?per_page={per_page}"
        next_url: str | None = self._resolve_url(url)
        while next_url:
            body, headers = self._request(next_url)
            data = json.loads(body.decode("utf-8")) if body else []
            if not isinstance(data, list):
                raise GitHubError(f"Expected list from {next_url}, got {type(data)}")
            yield data
            next_url = _parse_next_link(headers.get("link", ""))

    def get_all(self, path: str, *, per_page: int = 100) -> list[Any]:
        items: list[Any] = []
        for page in self.paginate(path, per_page=per_page):
            items.extend(page)
            if not page:
                break
        return items


def _parse_next_link(link_header: str) -> str | None:
    if not link_header:
        return None
    # Format: <url>; rel="next", <url>; rel="last"
    for part in link_header.split(","):
        section = part.strip()
        if 'rel="next"' not in section:
            continue
        start = section.find("<")
        end = section.find(">")
        if start != -1 and end != -1:
            return section[start + 1 : end]
    return None


def parse_repo(repo: str) -> tuple[str, str]:
    """Parse owner/name."""
    repo = repo.strip().strip("/")
    if repo.startswith("https://github.com/"):
        repo = repo.removeprefix("https://github.com/")
    parts = repo.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Invalid repo '{repo}'; expected owner/name")
    return parts[0], parts[1]


def repo_slug(repo: str) -> str:
    _owner, name = parse_repo(repo)
    return name
