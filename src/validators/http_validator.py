"""HTTP validation with rate limiting and soft-404 detection."""

from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urlparse

import httpx
from aiolimiter import AsyncLimiter

from ..config import RATE_LIMITS, SSO_REDIRECT_DOMAINS, SOFT_404_PATTERNS, settings
from ..models import ValidationResult


_SOFT_404_RE = re.compile("|".join(SOFT_404_PATTERNS), re.IGNORECASE)


def _domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _is_sso_redirect(urls: Iterable[str]) -> bool:
    for url in urls:
        netloc = _domain_from_url(url)
        for marker in SSO_REDIRECT_DOMAINS:
            if marker in netloc or marker in url:
                return True
    return False


class RateLimiter:
    def __init__(self) -> None:
        self._limiters: dict[str, AsyncLimiter] = {}

    def _get_rate(self, domain: str) -> int:
        if not domain:
            return RATE_LIMITS.get("default", settings.default_rate_limit)
        for key, value in RATE_LIMITS.items():
            if key != "default" and domain.endswith(key):
                return value
        return RATE_LIMITS.get("default", settings.default_rate_limit)

    def limiter_for(self, domain: str) -> AsyncLimiter:
        if domain not in self._limiters:
            rate = self._get_rate(domain)
            self._limiters[domain] = AsyncLimiter(rate, 60)
        return self._limiters[domain]


class HTTPClient:
    def __init__(self) -> None:
        self._limiter = RateLimiter()
        self._client = httpx.AsyncClient(
            timeout=settings.http_timeout,
            follow_redirects=True,
            headers={"User-Agent": settings.user_agent},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, url: str) -> httpx.Response:
        domain = _domain_from_url(url)
        limiter = self._limiter.limiter_for(domain)
        async with limiter:
            return await self._client.get(url)

    async def fetch_and_validate(self, url: str) -> tuple[ValidationResult, str]:
        try:
            response = await self._request(url)
            redirect_chain = [r.url.__str__() for r in response.history]
            final_url = str(response.url)
            status_code = response.status_code
            chain = redirect_chain + [final_url]
            is_sso = _is_sso_redirect(chain)
            body = response.text or ""
            is_soft_404 = False
            if status_code == 200:
                is_soft_404 = bool(_SOFT_404_RE.search(body))
            return (
                ValidationResult(
                    url=url,
                    final_url=final_url,
                    status_code=status_code,
                    redirect_chain=redirect_chain,
                    is_soft_404=is_soft_404,
                    is_sso_redirect=is_sso,
                    error=None,
                ),
                body,
            )
        except httpx.RequestError as exc:
            return (
                ValidationResult(
                    url=url,
                    final_url=url,
                    status_code=0,
                    redirect_chain=[],
                    is_soft_404=False,
                    is_sso_redirect=False,
                    error=str(exc),
                ),
                "",
            )

    async def validate(self, url: str) -> ValidationResult:
        validation, _ = await self.fetch_and_validate(url)
        return validation

    async def fetch_html(self, url: str) -> tuple[str, str, int]:
        response = await self._request(url)
        return response.text or "", str(response.url), response.status_code
