"""Wistia Stats API client — auth, session reuse, retry/backoff, pagination."""

import logging
from types import TracebackType
from typing import Any, Generator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.ingestion import config

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
        """GET a single resource. Raises HTTPError on 4xx/5xx after retries exhaust."""
        logger.info("GET %s params=%s", url, params)
        resp = self._session.get(url, params=params, timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()

    def paginate(
        self,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> Generator[list[dict[str, Any]], None, None]:
        """Yield successive pages until the endpoint returns an empty array."""
        base_params = dict(params or {})
        page = 1
        while True:
            resp = self._session.get(
                url,
                params={**base_params, "page": page},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            records: list[dict[str, Any]] = resp.json()
            if not records:
                logger.info("pagination complete url=%s total_pages=%d", url, page - 1)
                return
            logger.info("fetched page=%d records=%d url=%s", page, len(records), url)
            yield records
            page += 1


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
