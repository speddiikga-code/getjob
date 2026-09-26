"""HTTP client shared by all collectors: polite per-host delay, retries, browser headers."""

import threading
import time
from urllib.parse import urlsplit

import httpx

from getjob.settings import Settings

RETRY_STATUS = {429, 500, 502, 503, 504}


class Http:
    def __init__(self, settings: Settings, retries: int = 2) -> None:
        self._client = httpx.Client(
            headers={
                "User-Agent": settings.user_agent,
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            },
            timeout=settings.timeout,
            follow_redirects=True,
        )
        self._delay = settings.request_delay
        self._retries = retries
        self._last_request: dict[str, float] = {}
        self._lock = threading.Lock()

    def get(self, url: str, **kwargs) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        host = urlsplit(url).hostname or ""
        for attempt in range(self._retries + 1):
            self._wait_turn(host)
            try:
                resp = self._client.request(method, url, **kwargs)
            except httpx.RequestError:
                if attempt == self._retries:
                    raise
                time.sleep(2**attempt)
                continue
            if resp.status_code in RETRY_STATUS and attempt < self._retries:
                time.sleep(2**attempt)
                continue
            resp.raise_for_status()
            return resp
        raise AssertionError("unreachable")

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Http":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _wait_turn(self, host: str) -> None:
        """Keep at least `request_delay` seconds between requests to the same host."""
        with self._lock:
            now = time.monotonic()
            ready_at = self._last_request.get(host, 0.0) + self._delay
            self._last_request[host] = max(now, ready_at)
        if ready_at > now:
            time.sleep(ready_at - now)
