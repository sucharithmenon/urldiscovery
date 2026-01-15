"""Phase-1 careers URL resolver (company-site only)."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from ..extractors.domain import extract_domain, extract_homepage

CAREERS_HINTS = [
    "/careers",
    "/career",
    "/jobs",
    "/join",
    "/join-us",
    "/work-with-us",
    "/vacancies",
    "/talent",
]

ATS_DOMAINS = {
    "ashbyhq.com",
    "greenhouse.io",
    "job-boards.greenhouse.io",
    "lever.co",
    "myworkdayjobs.com",
    "smartrecruiters.com",
    "workable.com",
}

SOCIAL_DOMAINS = {
    "linkedin.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
}

JOB_TEXT_RE = re.compile(
    r"\b(jobs?|job openings?|openings|positions|vacancies|roles|career opportunities)\b",
    re.IGNORECASE,
)

SKIP_EXTENSIONS = (
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".zip",
)


@dataclass
class Phase1Result:
    company_name: str
    primary_domain: str
    careers_url: Optional[str]
    source: Optional[str]
    http_status: Optional[int]
    confidence: str
    notes: str


class RobotsCache:
    def __init__(self, client: "Phase1HTTPClient") -> None:
        self._client = client
        self._rules: dict[str, list[str]] = {}

    async def allowed(self, url: str) -> bool:
        domain = extract_domain(url)
        if not domain:
            return False
        if domain not in self._rules:
            self._rules[domain] = await self._fetch_rules(domain)
        path = urlparse(url).path or "/"
        for rule in self._rules[domain]:
            if path.startswith(rule):
                return False
        return True

    async def _fetch_rules(self, domain: str) -> list[str]:
        robots_url = f"https://{domain}/robots.txt"
        status, _, text, _ = await self._client.fetch(robots_url)
        if status >= 400 or not text:
            return []
        rules = []
        applies = False
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("user-agent:"):
                agent = line.split(":", 1)[1].strip()
                applies = agent == "*"
            if applies and line.lower().startswith("disallow:"):
                rule = line.split(":", 1)[1].strip() or "/"
                rules.append(rule)
        return rules


class Phase1HTTPClient:
    def __init__(
        self,
        global_limit: int = 50,
        per_domain_limit: int = 5,
        timeout: float = 12.0,
        retries: int = 1,
    ) -> None:
        self._global = asyncio.Semaphore(global_limit)
        self._per_domain_limit = per_domain_limit
        self._timeout = timeout
        self._retries = retries
        self._domain_semaphores: dict[str, asyncio.Semaphore] = {}
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    async def close(self) -> None:
        await self._client.aclose()

    def _domain_semaphore(self, domain: str) -> asyncio.Semaphore:
        if domain not in self._domain_semaphores:
            self._domain_semaphores[domain] = asyncio.Semaphore(self._per_domain_limit)
        return self._domain_semaphores[domain]

    async def fetch(self, url: str) -> tuple[int, str, str, int]:
        parsed = urlparse(url)
        domain = extract_domain(url) or parsed.netloc
        semaphore = self._domain_semaphore(domain)
        attempt = 0
        while True:
            attempt += 1
            async with self._global, semaphore:
                start = time.monotonic()
                try:
                    response = await self._client.get(url)
                    elapsed = int((time.monotonic() - start) * 1000)
                    return response.status_code, str(response.url), response.text or "", elapsed
                except httpx.RequestError:
                    if attempt > self._retries:
                        return 0, url, "", int((time.monotonic() - start) * 1000)
            if attempt <= self._retries:
                await asyncio.sleep(1.0)


class Phase1CareersResolver:
    def __init__(
        self,
        client: Optional[Phase1HTTPClient] = None,
        robots: Optional[RobotsCache] = None,
        max_depth: int = 2,
        max_pages: int = 50,
    ) -> None:
        self.client = client or Phase1HTTPClient()
        self.robots = robots or RobotsCache(self.client)
        self.max_depth = max_depth
        self.max_pages = max_pages

    async def resolve_one(
        self,
        company_name: str,
        primary_domain: str,
        website_url: Optional[str] = None,
        linkedin_url: Optional[str] = None,
    ) -> Phase1Result:
        notes = []
        primary_domain = (primary_domain or "").strip().lower()
        if not primary_domain and website_url:
            primary_domain = extract_domain(website_url) or ""
        if not primary_domain:
            return Phase1Result(company_name, "", None, None, None, "none", "missing_domain")

        start_url = self._normalize_start_url(website_url or "", primary_domain)
        if not start_url:
            start_url = f"https://{primary_domain}"

        source_hint = "company_site"
        status, final_url, html, _ = await self.client.fetch(start_url)
        if status != 200 or not self._same_domain(final_url, primary_domain):
            if linkedin_url:
                linkedin_site = await self._discover_site_from_social(linkedin_url, primary_domain)
                if linkedin_site:
                    source_hint = "social_redirect"
                    start_url = linkedin_site
                    status, final_url, html, _ = await self.client.fetch(start_url)
            if status != 200 or not self._same_domain(final_url, primary_domain):
                return Phase1Result(company_name, primary_domain, None, None, status or None, "none", "website_unreachable")

        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(final_url, 0)]
        candidates: list[tuple[str, str]] = []
        pages_seen = 0

        while queue and pages_seen < self.max_pages:
            url, depth = queue.pop(0)
            normalized = self._normalize_url(url)
            if normalized in visited:
                continue
            visited.add(normalized)
            if not await self.robots.allowed(url):
                continue

            status, final_page, body, _ = await self.client.fetch(url)
            if status != 200:
                continue
            if not self._same_domain(final_page, primary_domain):
                continue
            pages_seen += 1

            page_candidates = self._extract_career_candidates(body, final_page, primary_domain)
            candidates.extend(page_candidates)

            if depth >= self.max_depth:
                continue
            for link in self._extract_internal_links(body, final_page, primary_domain):
                if link not in visited:
                    queue.append((link, depth + 1))

        if not candidates:
            return Phase1Result(company_name, primary_domain, None, None, None, "none", "no_careers_links")

        best = await self._validate_candidates(candidates, primary_domain)
        if not best:
            return Phase1Result(company_name, primary_domain, None, None, None, "none", "careers_unverified")

        careers_url, source = best
        confidence = "high" if source == "company_site" else "medium"
        if source_hint == "social_redirect" and source == "company_site":
            source = "social_redirect"
            confidence = "low"

        status, final_url, _, _ = await self.client.fetch(careers_url)
        return Phase1Result(company_name, primary_domain, final_url, source, status, confidence, "")

    async def _validate_candidates(
        self,
        candidates: list[tuple[str, str]],
        primary_domain: str,
    ) -> Optional[tuple[str, str]]:
        scored: list[tuple[int, str, str]] = []
        for url, source in candidates:
            status, final_url, html, _ = await self.client.fetch(url)
            if status != 200:
                continue
            if source == "company_site" and not self._same_domain(final_url, primary_domain):
                continue
            if source == "linked_ats" and not self._is_ats_domain(final_url):
                continue
            if not self._has_job_content(html):
                continue
            score = self._score_careers_url(final_url, source)
            scored.append((score, final_url, source))
        if not scored:
            return None
        scored.sort(reverse=True)
        _, final_url, source = scored[0]
        return final_url, source

    def _score_careers_url(self, url: str, source: str) -> int:
        score = 100 if source == "company_site" else 80
        parsed = urlparse(url)
        path = parsed.path.lower()
        if parsed.netloc.startswith(("careers.", "jobs.")):
            score += 15
        if path in {"/careers", "/jobs"}:
            score += 20
        for hint in CAREERS_HINTS:
            if hint in path:
                score += 5
                break
        return score

    def _has_job_content(self, html: str) -> bool:
        if not html:
            return False
        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        return bool(JOB_TEXT_RE.search(text))

    def _extract_internal_links(self, html: str, base_url: str, primary_domain: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        links: list[str] = []
        for tag in soup.find_all("a", href=True):
            href = tag.get("href", "").strip()
            if not href or href.startswith("#"):
                continue
            if href.lower().startswith(("mailto:", "tel:", "javascript:")):
                continue
            full = urljoin(base_url, href)
            if full.endswith(SKIP_EXTENSIONS):
                continue
            if self._same_domain(full, primary_domain):
                links.append(full)
        return links

    def _extract_career_candidates(
        self,
        html: str,
        base_url: str,
        primary_domain: str,
    ) -> list[tuple[str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        candidates: list[tuple[str, str]] = []
        for tag in soup.find_all("a", href=True):
            href = tag.get("href", "").strip()
            text = tag.get_text(" ", strip=True).lower()
            if not href:
                continue
            full = urljoin(base_url, href)
            if self._is_ats_domain(full):
                if "career" in text or "job" in text:
                    candidates.append((full, "linked_ats"))
                continue
            if not self._same_domain(full, primary_domain):
                continue
            if any(hint in full.lower() for hint in CAREERS_HINTS) or "career" in text or "job" in text:
                candidates.append((full, "company_site"))
        return candidates

    async def _discover_site_from_social(self, linkedin_url: str, primary_domain: str) -> Optional[str]:
        status, final_url, html, _ = await self.client.fetch(linkedin_url)
        if status != 200:
            return None
        if self._same_domain(final_url, primary_domain):
            return final_url
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all("a", href=True):
            href = tag.get("href", "").strip()
            if not href:
                continue
            if self._is_social(href):
                continue
            if self._same_domain(href, primary_domain):
                return href
        return None

    def _normalize_start_url(self, website_url: str, primary_domain: str) -> str:
        url = website_url.strip()
        if not url:
            return ""
        parsed = urlparse(url)
        if not parsed.scheme:
            parsed = parsed._replace(scheme="https")
        normalized = urlunparse(parsed)
        if self._same_domain(normalized, primary_domain):
            return normalized
        return ""

    def _same_domain(self, url: str, primary_domain: str) -> bool:
        return extract_domain(url) == primary_domain

    def _normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        return urlunparse(parsed._replace(query="", fragment=""))

    def _is_ats_domain(self, url: str) -> bool:
        try:
            host = urlparse(url).netloc.lower()
        except Exception:
            return False
        return any(host.endswith(domain) for domain in ATS_DOMAINS)

    def _is_social(self, url: str) -> bool:
        try:
            host = urlparse(url).netloc.lower()
        except Exception:
            return False
        return any(host.endswith(domain) for domain in SOCIAL_DOMAINS)
