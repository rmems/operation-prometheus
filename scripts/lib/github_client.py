"""Rate-limit-aware read-only GitHub REST client (stdlib only)."""

from __future__ import annotations

import json
import logging
import os
import re
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


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Allow redirects only within the original HTTPS API origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        source = urllib.parse.urlsplit(req.full_url)
        target = urllib.parse.urlsplit(newurl)
        if target.scheme.casefold() != "https" or target.netloc.casefold() != source.netloc.casefold():
            raise GitHubError(
                f"Refusing GitHub API redirect from {source.netloc} to "
                f"{target.scheme or '(missing)'}://{target.netloc or '(missing)'}"
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


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
        self._opener = urllib.request.build_opener(_SafeRedirectHandler())
        if not self.token:
            logger.warning(
                "No GitHub token configured; unauthenticated rate limit is ~60 req/hr"
            )

    @classmethod
    def from_env(cls, env_name: str = "GITHUB_TOKEN") -> GitHubClient:
        """Load token from env. Default name GITHUB_TOKEN; falls back to GH_TOKEN."""
        token = os.environ.get(env_name) or None
        if not token and env_name == "GITHUB_TOKEN":
            # gh CLI commonly exports GH_TOKEN; bridge without printing secrets.
            token = os.environ.get("GH_TOKEN") or None
        return cls(token=token)

    def _headers(self, accept: str = "application/vnd.github+json") -> dict[str, str]:
        headers = {
            "Accept": accept,
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": API_VERSION,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def resolve_url(self, path_or_url: str) -> str:
        if path_or_url.startswith("https://"):
            return path_or_url
        if path_or_url.startswith("http://"):
            # Never use cleartext HTTP for API calls.
            return "https://" + path_or_url.removeprefix("http://")
        if not path_or_url.startswith("/"):
            path_or_url = "/" + path_or_url
        return self.base_url + path_or_url

    def _request(
        self,
        path_or_url: str,
        *,
        accept: str = "application/vnd.github+json",
    ) -> tuple[bytes, dict[str, str]]:
        url = self.resolve_url(path_or_url)
        # Bandit/Codacy: only permit HTTPS (never file:/ or custom schemes).
        if not url.startswith("https://"):
            raise GitHubError(f"Refusing non-HTTPS URL: {url[:80]}")
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(url, headers=self._headers(accept), method="GET")
            try:
                # Scheme already restricted to https:// above (Bandit B310).
                with self._opener.open(req, timeout=60) as resp:  # nosec B310
                    body = resp.read()
                    headers = {k.lower(): v for k, v in resp.headers.items()}
                    self._maybe_throttle(headers)
                    return body, headers
            except urllib.error.HTTPError as exc:
                last_err = exc
                status = exc.code
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                err_text = self._read_error_text(exc)

                if self._should_retry(status, exc, err_text, attempt):
                    delay = self._backoff_seconds(attempt, retry_after, exc, err_text)
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
                detail = err_text[:500]
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

    @staticmethod
    def _read_error_text(exc: urllib.error.HTTPError) -> str:
        """Read and decode an HTTPError body once, tolerating read failures."""
        try:
            err_body = exc.read()
        except Exception:
            err_body = b""
        return err_body.decode("utf-8", errors="replace")

    def _should_retry(
        self,
        status: int,
        exc: urllib.error.HTTPError,
        err_text: str,
        attempt: int,
    ) -> bool:
        if status == 403:
            return self._is_rate_limit_403(exc, err_text) and attempt < self.max_retries
        return status in (429, 500, 502, 503, 504) and attempt < self.max_retries

    @staticmethod
    def _is_rate_limit_403(exc: urllib.error.HTTPError, body_text: str = "") -> bool:
        """Check if a 403 error is rate-limit related (headers + cached body)."""
        if exc.headers:
            remaining = exc.headers.get("X-RateLimit-Remaining")
            if remaining is not None:
                try:
                    if int(remaining) == 0:
                        return True
                except ValueError:
                    pass
        text = (body_text or "").lower()
        return "rate limit" in text or "abuse detection" in text

    @staticmethod
    def _backoff_seconds(
        attempt: int,
        retry_after: str | None,
        exc: urllib.error.HTTPError,
        body_text: str = "",
    ) -> float:
        if retry_after:
            try:
                return float(retry_after) + 0.5
            except ValueError:
                pass
        if "secondary rate limit" in (body_text or "").lower():
            return 60.0
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

    def get_json_with_headers(self, path_or_url: str) -> tuple[Any, dict[str, str]]:
        body, headers = self._request(path_or_url)
        data = json.loads(body.decode("utf-8")) if body else None
        return data, headers

    def get_text(
        self,
        path_or_url: str,
        *,
        accept: str = "application/vnd.github.v3.diff",
    ) -> str:
        body, _ = self._request(path_or_url, accept=accept)
        return body.decode("utf-8", errors="replace")

    @staticmethod
    def _validate_graphql_document(document: str) -> None:
        named_query = re.match(r"^query\s+[_A-Za-z][_0-9A-Za-z]*\s*(?:\(|\{)", document)
        if not named_query or re.search(r"(?i)\bmutation\b", document):
            raise GitHubError("Refusing non-query GraphQL document")

    def _graphql_endpoint(self) -> str:
        if self.base_url.endswith("/api/v3"):
            graphql_url = self.base_url.removesuffix("/api/v3") + "/api/graphql"
        else:
            graphql_url = self.base_url + "/graphql"
        if not graphql_url.startswith("https://"):
            raise GitHubError(f"Refusing non-HTTPS GraphQL URL: {graphql_url[:80]}")
        return graphql_url

    @staticmethod
    def _graphql_data(parsed: Any) -> dict[str, Any]:
        if not isinstance(parsed, dict):
            raise GitHubError("GitHub GraphQL response was not an object")
        graphql_errors = parsed.get("errors") or []
        if graphql_errors:
            messages = [
                str(error.get("message") or error)
                for error in graphql_errors
                if isinstance(error, dict)
            ]
            detail = "; ".join(messages)[:500] or "unknown GraphQL error"
            raise GitHubError(f"GitHub GraphQL query failed: {detail}")
        data = parsed.get("data")
        if not isinstance(data, dict):
            raise GitHubError("GitHub GraphQL response has no data object")
        return data

    def query_graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Execute one explicitly read-only GitHub GraphQL query.

        GitHub transports GraphQL queries over HTTP POST, but this collector must
        never expose a mutation surface.  Callers therefore provide a complete,
        named ``query`` document; anonymous documents and documents containing a
        ``mutation`` operation are rejected before any network request occurs.
        """
        document = query.strip()
        self._validate_graphql_document(document)
        graphql_url = self._graphql_endpoint()

        payload = json.dumps(
            {"query": document, "variables": variables or {}},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        headers = self._headers()
        headers["Content-Type"] = "application/json"
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(
                graphql_url,
                data=payload,
                headers=headers,
                method="POST",
            )
            try:
                with self._opener.open(req, timeout=60) as resp:  # nosec B310
                    body = resp.read()
                    response_headers = {k.lower(): v for k, v in resp.headers.items()}
                    self._maybe_throttle(response_headers)
                    parsed = json.loads(body.decode("utf-8")) if body else {}
                    return self._graphql_data(parsed), response_headers
            except urllib.error.HTTPError as exc:
                last_err = exc
                status = exc.code
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                err_text = self._read_error_text(exc)
                if self._should_retry(status, exc, err_text, attempt):
                    delay = self._backoff_seconds(attempt, retry_after, exc, err_text)
                    logger.warning(
                        "GitHub GraphQL %s; retry %s/%s after %.1fs",
                        status,
                        attempt + 1,
                        self.max_retries,
                        delay,
                    )
                    self._sleep(delay)
                    continue
                raise GitHubError(
                    f"GitHub GraphQL request failed with {status}: {err_text[:500]}",
                    status=status,
                ) from exc
            except urllib.error.URLError as exc:
                last_err = exc
                if attempt < self.max_retries:
                    delay = min(60.0, 2.0**attempt)
                    logger.warning(
                        "GraphQL network error: %s; retry after %.1fs",
                        exc,
                        delay,
                    )
                    self._sleep(delay)
                    continue
                raise GitHubError(f"GitHub GraphQL network error: {exc}") from exc
        raise GitHubError(f"GitHub GraphQL query failed after retries: {last_err}")

    def paginate(self, path: str, *, per_page: int = 100) -> Iterator[list[Any]]:
        """Yield pages of list results, following Link rel=next."""
        if "?" in path:
            url = f"{path}&per_page={per_page}"
        else:
            url = f"{path}?per_page={per_page}"
        next_url: str | None = self.resolve_url(url)
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
    """Filesystem-safe slug including owner to avoid cross-org collisions."""
    owner, name = parse_repo(repo)
    return f"{owner}_{name}"
