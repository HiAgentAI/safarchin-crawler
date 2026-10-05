import asyncio
import logging
from typing import Optional, Dict, Any
from curl_cffi.requests import AsyncSession
import httpx

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

class ResilientHttpClient:
    """
    Resilient HTTP Client with TLS impersonation (JA3/JA4 fingerprinting)
    via curl_cffi to prevent bot blocks from Alibaba, FlyToday and Karnaval.
    """

    def __init__(
        self,
        impersonate: str = "chrome120",
        timeout: float = 15.0,
        retries: int = 2,
        proxy: Optional[str] = None,
    ):
        self.impersonate = impersonate
        self.timeout = timeout
        self.retries = retries
        self.proxy = proxy
        self._session: Optional[AsyncSession] = None

    async def get_session(self) -> AsyncSession:
        if self._session is None:
            self._session = AsyncSession(
                impersonate=self.impersonate,
                timeout=self.timeout,
                proxy=self.proxy,
            )
        return self._session

    async def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        merged_headers = {**DEFAULT_HEADERS, **(headers or {})}
        session = await self.get_session()

        for attempt in range(1, self.retries + 2):
            try:
                response = await session.get(url, params=params, headers=merged_headers)
                response.raise_for_status()
                return response
            except Exception as e:
                logger.warning(f"HTTP GET attempt {attempt}/{self.retries + 1} failed for {url}: {e}")
                if attempt > self.retries:
                    raise
                await asyncio.sleep(0.5 * attempt)

    async def post(
        self,
        url: str,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Any:
        merged_headers = {**DEFAULT_HEADERS, **(headers or {})}
        session = await self.get_session()
        body_json = json if json is not None else json_data

        for attempt in range(1, self.retries + 2):
            try:
                response = await session.post(url, json=body_json, data=data, headers=merged_headers)
                response.raise_for_status()
                return response
            except Exception as e:
                logger.warning(f"HTTP POST attempt {attempt}/{self.retries + 1} failed for {url}: {e}")
                if attempt > self.retries:
                    raise
                await asyncio.sleep(0.5 * attempt)

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None
