"""Wistia Stats API client — auth, session reuse, retry/backoff, pagination."""

import logging
from types import TracebackType
from typing import Any, Generator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.ingestion import config
from src.ingestion.errors import (
    WistiaAPIError,
    WistiaAuthError,
    WistiaError,
    WistiaNotFoundError,
)

logger = logging.getLogger(__name__)

_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class WistiaClient:
    """Wistia Stats API client with session reuse, retry/backoff, and page-based pagination."""

    def __init__(self, api_token: str, timeout: int = config.REQUEST_TIMEOUT) -> None:
        self._timeout = timeout
        self._session = _build_session(api_token)

    # ── Context manager ────────────────────────────────────────────────────────

    def __enter__(self) -> "WistiaClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._session.close()

    # ── HTTP helpers ───────────────────────────────────────────────────────────

    def get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """GET a single resource, returning parsed JSON. Raises a WistiaError on failure."""
        logger.info("GET %s params=%s", url, params)
        return self._request(url, params).json()

    def paginate(
        self,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> Generator[list[dict[str, Any]], None, None]:
        """Yield successive pages until the endpoint returns an empty array."""
        base_params = dict(params or {})
        page = 1
        while True:
            resp = self._request(url, {**base_params, "page": page})
            records: list[dict[str, Any]] = resp.json()
            if not records:
                logger.info("pagination complete url=%s total_pages=%d", url, page - 1)
                return
            logger.info("fetched page=%d records=%d url=%s", page, len(records), url)
            yield records
            page += 1

    def _request(self, url: str, params: dict[str, Any] | None) -> requests.Response:
        """Perform a GET, translating any failure into a WistiaError."""
        try:
            resp = self._session.get(url, params=params, timeout=self._timeout)
            resp.raise_for_status()
        except requests.HTTPError as exc:
            raise _translate_http_error(exc, url) from exc
        except requests.RequestException as exc:
            logger.error("request failed url=%s error=%s", url, exc)
            raise WistiaAPIError(f"request to {url} failed: {exc}") from exc
        return resp


def _build_session(api_token: str) -> requests.Session:
    retry = Retry(
        total=5,
        backoff_factor=1,  # delays: 1s, 2s, 4s, 8s, 16s
        status_forcelist=_RETRY_STATUSES,
        allowed_methods=["GET"],
        raise_on_status=False,  # let raise_for_status() handle final errors uniformly
    )
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
        }
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _translate_http_error(exc: requests.HTTPError, url: str) -> WistiaError:
    """Map an HTTP error response to the appropriate WistiaError subclass."""
    status = exc.response.status_code if exc.response is not None else None
    logger.error("HTTP error url=%s status=%s", url, status)
    if status == 401:
        return WistiaAuthError("authentication failed (401) — check WISTIA_API_TOKEN")
    if status == 404:
        return WistiaNotFoundError(f"resource not found (404): {url}")
    return WistiaAPIError(f"unexpected HTTP {status} from {url}")
