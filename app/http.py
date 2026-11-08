import asyncio
from collections import defaultdict
from urllib.parse import urlsplit
import httpx
from app.config import settings

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRY_AFTER_SECONDS = 60


class Http:
    """Shared HTTP client: one request at a time per host, spaced out, with retries and backoff."""

    def __init__(self, client: httpx.AsyncClient, min_interval: float | None = None, retries: int | None = None):
        self.client = client
        self.min_interval = settings.min_request_interval_seconds if min_interval is None else min_interval
        self.retries = settings.http_retries if retries is None else retries
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last: dict[str, float] = {}

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        host = urlsplit(url).hostname or ""
        loop = asyncio.get_running_loop()
        for attempt in range(self.retries + 1):
            response, error = None, None
            async with self._locks[host]:
                wait = self._last.get(host, 0) + self.min_interval - loop.time()
                if wait > 0:
                    await asyncio.sleep(wait)
                try:
                    response = await self.client.request(method, url, **kwargs)
                except httpx.TransportError as exc:
                    error = exc
                finally:
                    self._last[host] = loop.time()
            retryable = error is not None or response.status_code in RETRY_STATUSES
            if not retryable or attempt == self.retries:
                if error is not None:
                    raise error
                response.raise_for_status()
                return response
            await asyncio.sleep(_retry_delay(response, attempt))
        raise AssertionError("unreachable")

    async def get_json(self, url: str, **kwargs):
        return (await self.request("GET", url, **kwargs)).json()

    async def post_json(self, url: str, json, **kwargs):
        return (await self.request("POST", url, json=json, **kwargs)).json()


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After", "")
        if retry_after.isdigit():
            return min(int(retry_after), MAX_RETRY_AFTER_SECONDS)
    return 2 * 2 ** attempt
