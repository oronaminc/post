"""예의 바른(polite) 공용 HTTP 클라이언트.

- 도구를 식별하는 User-Agent
- 호스트별 요청 간 최소 간격(rate limit)
- 429 / 5xx / 타임아웃에 지수 백오프 재시도
- 리다이렉트 자동 추적 (NHK 의 .nhk 도메인 리다이렉트 등)

스크래핑 대상 사이트에 부담을 주지 않기 위한 최소한의 매너 장치다.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx

log = logging.getLogger("jptrend.http")


class PoliteClient:
    def __init__(
        self,
        user_agent: str,
        default_delay: float = 1.5,
        timeout: float = 20.0,
        max_retries: int = 3,
        host_delays: Optional[dict[str, float]] = None,
    ):
        self.default_delay = default_delay
        self.max_retries = max_retries
        self.host_delays = host_delays or {}
        self._last_request: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": user_agent,
                "Accept-Language": "ja,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
            },
            timeout=timeout,
            follow_redirects=True,
        )

    def _lock_for(self, host: str) -> asyncio.Lock:
        if host not in self._locks:
            self._locks[host] = asyncio.Lock()
        return self._locks[host]

    async def _throttle(self, host: str) -> None:
        delay = self.host_delays.get(host, self.default_delay)
        elapsed = time.monotonic() - self._last_request.get(host, 0.0)
        wait = delay - elapsed
        if wait > 0:
            await asyncio.sleep(wait)

    async def get(self, url: str, **kwargs) -> httpx.Response:
        """호스트별 rate limit + 재시도를 적용한 GET."""
        host = httpx.URL(url).host or "_"
        async with self._lock_for(host):
            await self._throttle(host)
            try:
                return await self._get_with_retry(url, **kwargs)
            finally:
                self._last_request[host] = time.monotonic()

    async def _get_with_retry(self, url: str, **kwargs) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = await self._client.get(url, **kwargs)
                if resp.status_code in (429, 500, 502, 503, 504):
                    backoff = 2 ** attempt
                    log.warning(
                        "%s -> HTTP %s, %ss 후 재시도(%d/%d)",
                        url, resp.status_code, backoff, attempt + 1, self.max_retries,
                    )
                    await asyncio.sleep(backoff)
                    last_exc = httpx.HTTPStatusError(
                        f"HTTP {resp.status_code}", request=resp.request, response=resp
                    )
                    continue
                return resp
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                backoff = 2 ** attempt
                log.warning("%s 요청 실패(%s), %ss 후 재시도", url, exc, backoff)
                await asyncio.sleep(backoff)
        if last_exc:
            raise last_exc
        raise RuntimeError(f"요청 실패: {url}")

    async def get_text(self, url: str, **kwargs) -> str:
        resp = await self.get(url, **kwargs)
        resp.raise_for_status()
        return resp.text

    async def get_bytes(self, url: str, **kwargs) -> bytes:
        resp = await self.get(url, **kwargs)
        resp.raise_for_status()
        return resp.content

    async def aclose(self) -> None:
        await self._client.aclose()
