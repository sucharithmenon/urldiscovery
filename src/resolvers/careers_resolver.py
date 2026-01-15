"""Careers URL resolver for ATS URLs."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, urlunparse, urljoin
import time

from bs4 import BeautifulSoup

from ..extractors.company_name import extract as extract_company_name
from ..extractors.corporate_url import (
    extract as extract_corporate_url,
    extract_homepage,
    is_valid_corporate_url,
)
from ..extractors.domain import extract_domain
from ..validators.http_validator import HTTPClient
from ..validators.ats_root_validator import _extract_job_links
from ..patterns.ats_patterns import detect

SOCIAL_DOMAINS = {
    "linkedin.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
}

CAREERS_PATH_HINTS = [
    "/careers",
    "/career",
    "/jobs",
    "/join",
    "/join-us",
    "/joinus",
    "/work-with-us",
    "/workwithus",
    "/talent",
    "/vacancies",
]

APPLY_COMPANY_TEXT = [
    "apply on company site",
    "apply on company website",
    "apply on company page",
    "apply on company",
    "apply on website",
]

PROVIDER_PATTERNS = {
    "GREENHOUSE": [
        re.compile(r"https?://boards\.greenhouse\.io/(?P<handle>[^/?#]+)", re.IGNORECASE),
        re.compile(r"https?://job-boards\.greenhouse\.io/(?P<handle>[^/?#]+)", re.IGNORECASE),
    ],
    "WORKABLE": [
        re.compile(r"https?://apply\.workable\.com/(?P<handle>[^/?#]+)/?(jobs)?", re.IGNORECASE),
    ],
    "WORKDAY": [
        re.compile(r"https?://[^/]+\.myworkdayjobs\.com/.*", re.IGNORECASE),
    ],
    "SMARTRECRUITERS": [
        re.compile(r"https?://careers\.smartrecruiters\.com/(?P<handle>[^/?#]+)", re.IGNORECASE),
    ],
    "LEVER": [
        re.compile(r"https?://jobs\.lever\.co/(?P<handle>[^/?#]+)", re.IGNORECASE),
        re.compile(r"https?://(?P<handle>[^./]+)\.lever\.co/?", re.IGNORECASE),
    ],
    "ASHBY": [
        re.compile(r"https?://jobs\.ashbyhq\.com/(?P<handle>[^/?#]+)", re.IGNORECASE),
    ],
}

ATS_FAMILIES = {
    "PUBLIC_ATS": [
        "LEVER",
        "GREENHOUSE",
        "WORKABLE",
        "ASHBY",
        "SMARTRECRUITERS",
        "RECRUITEE",
        "TEAMTAILOR",
    ],
    "ENTERPRISE_ATS": [
        "WORKDAY",
        "SAP_SUCCESSFACTORS",
        "ORACLE_TALEO",
        "ORACLE_CLOUD_HCM",
        "UKG",
        "ICIMS",
        "ADP_WORKFORCE_NOW",
    ],
    "HRIS_HYBRID": [
        "BAMBOOHR",
        "HIBOB",
        "DARWINBOX",
        "PAYLOCITY",
        "PEOPLESTRONG",
        "KEKA",
        "ZOHO_RECRUIT",
    ],
    "INTERNAL_PLATFORMS": [
        "META",
        "APPLE",
        "AMAZON",
    ],
    "LONG_TAIL_ATS": [
        "JAZZHR",
        "BREEZY_HR",
        "PINPOINT",
        "HUNDRED_HIRES",
        "BETTERTEAM",
        "RECOOTY",
        "JOIN_DOT_COM",
        "MANATAL",
        "RECRUITERFLOW",
        "HIRINGTHING",
        "CAREERPLUG",
    ],
}

ATS_FAMILY_EXPECTATIONS = {
    "PUBLIC_ATS": {
        "expected_primary": "RESOLVED",
        "notes": "Most companies publish a public careers page",
    },
    "ENTERPRISE_ATS": {
        "expected_primary": "PARTIAL",
        "notes": "Hiring often ATS-only; public careers pages frequently absent",
    },
    "HRIS_HYBRID": {
        "expected_primary": "PARTIAL",
        "notes": "Jobs embedded in HR portals; limited outbound links",
    },
    "INTERNAL_PLATFORMS": {
        "expected_primary": "PARTIAL",
        "notes": "Careers tightly controlled on proprietary domains",
    },
}


@dataclass
class Candidate:
    url: str
    source: str
    score: int
    text: str = ""
    apply_only: bool = False


@dataclass
class ResolveResult:
    company_ats_name: str
    company_ats_url: str
    company_name_clean: str
    company_domain: str
    corporate_url: str


@dataclass
class DebugInfo:
    status: str
    confidence: float
    evidence: dict
    fetches: list[dict]
    notes: list[str]


def normalize_ats_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme:
        parsed = parsed._replace(scheme="https")
    cleaned = parsed._replace(query="", fragment="")
    normalized = urlunparse(cleaned)
    return normalized.rstrip("/")


def detect_provider(url: str) -> str:
    for provider, patterns in PROVIDER_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(url):
                return provider
    detection = detect(url)
    if detection:
        name, _ = detection
        return name.upper()
    return "UNKNOWN"


def ats_family(ats_name: str) -> str:
    name = (ats_name or "").upper()
    for family, providers in ATS_FAMILIES.items():
        if name in providers:
            return family
    return "UNKNOWN"


def expected_outcome(family: str) -> dict:
    return ATS_FAMILY_EXPECTATIONS.get(family, {"expected_primary": "", "notes": ""})


def normalize_domain(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if not raw.startswith("http"):
        raw = f"https://{raw}"
    return extract_domain(raw)


def is_social(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    return any(host.endswith(domain) for domain in SOCIAL_DOMAINS)


def _score_link(text: str) -> int:
    if not text:
        return 0
    lowered = text.lower()
    if "company website" in lowered or "website" in lowered:
        return 5
    if "about" in lowered or "company" in lowered:
        return 4
    if "careers" in lowered or "jobs" in lowered:
        return 3
    return 1


def _is_apply_link_text(text: str) -> bool:
    if not text:
        return False
    lowered = " ".join(text.lower().split())
    return any(term in lowered for term in APPLY_COMPANY_TEXT)


def _location_score(tag: Optional[str]) -> int:
    if not tag:
        return 0
    if tag in {"header", "footer", "nav"}:
        return 4
    return 1


def _iter_link_candidates(html: str, base_url: str) -> list[Candidate]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[Candidate] = []

    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        if not href:
            continue
        full = href if href.startswith("http") else urljoin(base_url, href)
        text = link.get_text(" ", strip=True)
        if not full or is_social(full) or not is_valid_corporate_url(full):
            continue
        classes = " ".join(link.get("class", [])).lower()
        source = "ATS_ROOT_LINK"
        if "logo" in classes or "brand" in classes:
            source = "LOGO_LINK"
        parent = link.find_parent(["header", "footer", "nav"])
        tag_name = parent.name if parent else None
        if tag_name == "footer":
            source = "FOOTER"
        elif tag_name in {"header", "nav"}:
            source = "HEADER_NAV"
        apply_only = _is_apply_link_text(text)
        score = _score_link(text) + _location_score(tag_name)
        if apply_only:
            score = min(score, 1)
        candidates.append(Candidate(full, source, score, text, apply_only=apply_only))
    return candidates


def _choose_domain_candidate(candidates: list[Candidate]) -> Optional[Candidate]:
    if not candidates:
        return None
    return sorted(candidates, key=lambda c: c.score, reverse=True)[0]


def _link_is_careers(url: str, text: str) -> bool:
    lowered = text.lower() if text else ""
    if "careers" in lowered or "jobs" in lowered:
        return True
    parsed = urlparse(url)
    if parsed.netloc.startswith(("careers.", "jobs.")):
        return True
    path = parsed.path.lower()
    return any(hint in path for hint in CAREERS_PATH_HINTS)


class CareersResolver:
    def __init__(self, client: Optional[HTTPClient] = None, max_fetches: int = 4) -> None:
        self.client = client or HTTPClient()
        self.max_fetches = max_fetches

    async def resolve_one(
        self,
        company_ats_url: str,
        company_ats_name: Optional[str] = None,
        master_company_domain: Optional[str] = None,
        fallback_homepage: bool = False,
        allow_master_override: bool = False,
        enable_sitemap_scan: bool = False,
    ) -> tuple[ResolveResult, DebugInfo]:
        ats_url = normalize_ats_url(company_ats_url)
        provider = company_ats_name or detect_provider(ats_url)
        master_domain = normalize_domain(master_company_domain)

        debug = DebugInfo(
            status="ERROR",
            confidence=0.0,
            evidence={
                "domain_source": "MASTER_DB" if master_domain else "",
                "careers_source": "NONE",
                "observed_urls": [],
            },
            fetches=[],
            notes=[],
        )

        def observe(url: str, url_type: str, reason: str) -> None:
            debug.evidence["observed_urls"].append(
                {"url": url, "type": url_type, "reason": reason}
            )

        async def fetch(url: str) -> tuple[object, str]:
            start = time.monotonic()
            validation, html = await self.client.fetch_and_validate(url)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            debug.fetches.append(
                {
                    "url": url,
                    "status": validation.status_code,
                    "final_url": validation.final_url,
                    "elapsed_ms": elapsed_ms,
                }
            )
            return validation, html

        if len(debug.fetches) >= self.max_fetches:
            return (
                ResolveResult(provider, ats_url, "", master_domain or "", ""),
                debug,
            )

        ats_validation, ats_html = await fetch(ats_url)
        if ats_validation.status_code <= 0:
            debug.status = "ERROR"
            debug.notes.append("ats_fetch_error")
            return (
                ResolveResult(provider, ats_url, "", master_domain or "", ""),
                debug,
            )
        if ats_validation.status_code >= 400:
            debug.notes.append("ats_not_found")
            if master_domain and len(debug.fetches) < self.max_fetches:
                careers_url = await self._scan_corporate_home(
                    master_domain,
                    fetch,
                )
                if careers_url:
                    debug.status = "RESOLVED"
                    debug.evidence["domain_source"] = "MASTER_DB"
                    debug.evidence["careers_source"] = "CORP_HOME_SCAN"
                    return (
                        ResolveResult(provider, ats_url, "", master_domain, careers_url),
                        debug,
                    )
                if enable_sitemap_scan and len(debug.fetches) < self.max_fetches:
                    sitemap_url, sitemap_candidates, sitemap_notes, sitemap_locale = await self._scan_sitemap(
                        master_domain,
                        fetch,
                        len(debug.fetches),
                        self.max_fetches,
                    )
                    if sitemap_url:
                        debug.evidence["sitemap_url"] = sitemap_url
                        debug.evidence["sitemap_candidates"] = sitemap_candidates
                    debug.notes.extend(sitemap_notes)
                    if sitemap_candidates:
                        debug.status = "RESOLVED"
                        debug.evidence["domain_source"] = "MASTER_DB"
                        debug.evidence["careers_source"] = "CORP_SITEMAP"
                        debug.confidence = 0.75 if sitemap_locale else 0.85
                        return (
                            ResolveResult(provider, ats_url, "", master_domain, sitemap_candidates[0]),
                            debug,
                        )
                debug.status = "PARTIAL"
                debug.evidence["domain_source"] = "MASTER_DB"
                return (
                    ResolveResult(provider, ats_url, "", master_domain, ""),
                    debug,
                )
            debug.status = "NOT_FOUND"
            return (
                ResolveResult(provider, ats_url, "", "", ""),
                debug,
            )

        company_name = extract_company_name(ats_html, slug=None, mode="strict") or ""

        candidates = _iter_link_candidates(ats_html, ats_validation.final_url)
        for candidate in candidates:
            observe(candidate.url, "CORP", candidate.source)

        homepage_candidate = extract_homepage(ats_html, ats_validation.final_url)
        if homepage_candidate and homepage_candidate.value:
            url_type = (
                "SOCIAL"
                if is_social(homepage_candidate.value)
                else "CORP"
                if is_valid_corporate_url(homepage_candidate.value)
                else "ATS"
            )
            observe(homepage_candidate.value, url_type, "JSON_LD")
            if is_valid_corporate_url(homepage_candidate.value) and not is_social(homepage_candidate.value):
                candidates.append(
                    Candidate(
                        homepage_candidate.value,
                        "JSON_LD" if homepage_candidate.source == "json-ld" else "ATS_ROOT_LINK",
                        4,
                        "",
                    )
                )

        careers_candidate = extract_corporate_url(ats_html, ats_validation.final_url)
        if careers_candidate and careers_candidate.value:
            url_type = (
                "SOCIAL"
                if is_social(careers_candidate.value)
                else "CORP"
                if is_valid_corporate_url(careers_candidate.value)
                else "ATS"
            )
            observe(
                careers_candidate.value,
                url_type,
                "ATS_ROOT_CAREERS",
            )
            if (
                careers_candidate.value
                and is_valid_corporate_url(careers_candidate.value)
                and not is_social(careers_candidate.value)
                and careers_candidate.source != "apply-link"
            ):
                candidates.append(Candidate(careers_candidate.value, "ATS_ROOT_LINK", 5, "careers"))

        chosen_domain = master_domain
        chosen_domain_source = "MASTER_DB" if master_domain else None
        detected_domain = None
        detected_source = None
        non_apply_candidates = [c for c in candidates if not c.apply_only]
        best_candidate = _choose_domain_candidate(non_apply_candidates)
        if best_candidate:
            candidate_domain = extract_domain(best_candidate.url)
            if candidate_domain:
                detected_domain = candidate_domain
                detected_source = best_candidate.source
                if not master_domain:
                    chosen_domain = candidate_domain
                    chosen_domain_source = best_candidate.source
        if chosen_domain_source:
            debug.evidence["domain_source"] = chosen_domain_source

        if master_domain and detected_domain and master_domain != detected_domain:
            if allow_master_override:
                chosen_domain = detected_domain
                chosen_domain_source = detected_source
                debug.evidence["domain_source"] = detected_source or "ATS_ROOT_LINK"
                debug.notes.append("master_override")
            else:
                debug.status = "CONFLICT"
                debug.evidence["domain_source"] = "MASTER_DB"
                debug.notes.append("domain_conflict")
                return (
                    ResolveResult(provider, ats_url, company_name, master_domain, ""),
                    debug,
                )

        corporate_url = ""
        home_scan_attempted = False
        if chosen_domain:
            for candidate in sorted(candidates, key=lambda c: c.score, reverse=True):
                if extract_domain(candidate.url) != chosen_domain:
                    continue
                if candidate.apply_only:
                    continue
                if _link_is_careers(candidate.url, candidate.text):
                    corporate_url = candidate.url
                    debug.evidence["careers_source"] = candidate.source
                    break
            if not corporate_url and len(debug.fetches) < self.max_fetches:
                home_scan_attempted = True
                corporate_url = await self._scan_corporate_home(
                    chosen_domain,
                    fetch,
                )
                if corporate_url:
                    debug.evidence["careers_source"] = "CORP_HOME_SCAN"

            if not corporate_url and fallback_homepage and not master_domain:
                corporate_url = f"https://{chosen_domain}"
                debug.notes.append("homepage_fallback")


        if not chosen_domain and len(debug.fetches) < self.max_fetches:
            job_links = _extract_job_links(ats_html, ats_validation.final_url, provider)
            for job_url in list(job_links)[:1]:
                job_validation, job_html = await fetch(job_url)
                if job_validation.status_code >= 400:
                    continue
                job_home = extract_homepage(job_html, job_validation.final_url)
                job_careers = extract_corporate_url(job_html, job_validation.final_url)
                if job_home and job_home.value:
                    observe(job_home.value, "CORP" if is_valid_corporate_url(job_home.value) else "ATS", "JOB_DETAIL_JSON")
                if job_careers and job_careers.value:
                    observe(job_careers.value, "CORP" if is_valid_corporate_url(job_careers.value) else "ATS", "JOB_DETAIL_LINK")
                if (
                    job_home
                    and job_home.value
                    and is_valid_corporate_url(job_home.value)
                    and not is_social(job_home.value)
                ):
                    chosen_domain = extract_domain(job_home.value)
                    if chosen_domain:
                        debug.evidence["domain_source"] = "JOB_DETAIL_JSON"
                        corporate_url = ""
                        break
                if (
                    job_careers
                    and job_careers.value
                    and is_valid_corporate_url(job_careers.value)
                    and not is_social(job_careers.value)
                    and job_careers.source != "apply-link"
                ):
                    chosen_domain = extract_domain(job_careers.value) or chosen_domain
                    if chosen_domain:
                        debug.evidence["domain_source"] = debug.evidence.get("domain_source") or "JOB_DETAIL_LINK"
                        if _link_is_careers(job_careers.value, ""):
                            corporate_url = job_careers.value
                            debug.evidence["careers_source"] = "JOB_DETAIL_LINK"
                            break


        if (
            enable_sitemap_scan
            and chosen_domain
            and not corporate_url
            and home_scan_attempted
            and len(debug.fetches) < self.max_fetches
        ):
            sitemap_url, sitemap_candidates, sitemap_notes, sitemap_locale = await self._scan_sitemap(
                chosen_domain,
                fetch,
                len(debug.fetches),
                self.max_fetches,
            )
            if sitemap_url:
                debug.evidence["sitemap_url"] = sitemap_url
                debug.evidence["sitemap_candidates"] = sitemap_candidates
            debug.notes.extend(sitemap_notes)
            if sitemap_candidates:
                corporate_url = sitemap_candidates[0]
                debug.evidence["careers_source"] = "CORP_SITEMAP"
                debug.confidence = 0.75 if sitemap_locale else 0.85

        if chosen_domain and corporate_url:
            debug.status = "RESOLVED"
        elif chosen_domain:
            debug.status = "PARTIAL"
        else:
            debug.status = "NOT_FOUND"

        if debug.confidence == 0.0:
            confidence = 0.3
            if chosen_domain:
                confidence += 0.4
            if corporate_url:
                confidence += 0.2
            if master_domain:
                confidence += 0.1
            debug.confidence = min(confidence, 1.0)

        return (
            ResolveResult(provider, ats_url, company_name, chosen_domain or "", corporate_url),
            debug,
        )

    async def resolve_batch(
        self,
        inputs: list[dict],
        concurrency: int = 5,
        fallback_homepage: bool = False,
        allow_master_override: bool = False,
        enable_sitemap_scan: bool = False,
    ) -> list[tuple[ResolveResult, DebugInfo]]:
        semaphore = asyncio.Semaphore(concurrency)

        async def run_one(row: dict) -> tuple[ResolveResult, DebugInfo]:
            async with semaphore:
                return await self.resolve_one(
                    company_ats_url=row.get("company_ats_url", ""),
                    company_ats_name=row.get("company_ats_name"),
                    master_company_domain=row.get("master_company_domain"),
                    fallback_homepage=fallback_homepage,
                    allow_master_override=allow_master_override,
                    enable_sitemap_scan=enable_sitemap_scan,
                )

        tasks = [asyncio.create_task(run_one(row)) for row in inputs]
        return await asyncio.gather(*tasks)

    async def _scan_corporate_home(
        self,
        domain: str,
        fetch,
    ) -> str:
        homepage_url = f"https://www.{domain}"
        validation, html = await fetch(homepage_url)
        if validation.status_code >= 400:
            return ""
        soup = BeautifulSoup(html, "html.parser")
        candidates: list[Candidate] = []
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            full = href if href.startswith("http") else urljoin(validation.final_url, href)
            if extract_domain(full) != domain:
                continue
            text = link.get_text(" ", strip=True)
            if _link_is_careers(full, text):
                candidates.append(Candidate(full, "CORP_HOME_SCAN", _score_link(text), text))
        if candidates:
            def rank(candidate: Candidate) -> tuple[int, int, int, int]:
                path = urlparse(candidate.url).path.lower()
                exact = 1 if path in {"/careers", "/jobs"} else 0
                subdomain = 1 if urlparse(candidate.url).netloc.startswith(("careers.", "jobs.")) else 0
                length = -len(path)
                return (exact, subdomain, candidate.score, length)
            return sorted(candidates, key=rank, reverse=True)[0].url
        return ""

    async def _scan_sitemap(
        self,
        domain: str,
        fetch,
        fetch_count: int,
        max_fetches: int,
    ) -> tuple[str, list[str], list[str], bool]:
        notes: list[str] = []
        sitemap_url = f"https://www.{domain}/sitemap.xml"
        if fetch_count >= max_fetches:
            notes.append("sitemap_budget_exhausted")
            return sitemap_url, [], notes, False
        validation, html = await fetch(sitemap_url)
        if validation.status_code >= 400:
            notes.append("sitemap_missing")
            return sitemap_url, [], notes, False
        if not html:
            notes.append("sitemap_empty")
            return sitemap_url, [], notes, False

        soup = BeautifulSoup(html, "xml")
        locs = [loc.get_text(" ", strip=True) for loc in soup.find_all("loc")]
        if not locs:
            notes.append("sitemap_invalid")
            return sitemap_url, [], notes, False

        if soup.find("sitemapindex"):
            notes.append("sitemap_index_encountered")
            return sitemap_url, [], notes, False

        candidates = []
        for link in locs:
            if extract_domain(link) != domain:
                continue
            path = urlparse(link).path.lower()
            if any(token in path for token in ("/blog", "/news", "/press", "/insights", "/articles")):
                continue
            if _link_is_careers(link, ""):
                candidates.append(link)

        if not candidates:
            notes.append("sitemap_no_careers")
            return sitemap_url, [], notes, False

        def rank(url: str) -> tuple[int, int, int]:
            parsed = urlparse(url)
            path = parsed.path.lower()
            exact = 1 if path in {"/careers", "/jobs"} else 0
            subdomain = 1 if parsed.netloc.startswith(("careers.", "jobs.")) else 0
            length = -len(path)
            return (exact, subdomain, length)

        candidates = sorted(candidates, key=rank, reverse=True)
        best = candidates[0]
        locale_specific = "/careers/" in best or "/jobs/" in best
        return sitemap_url, candidates[:20], notes, locale_specific


def load_inputs(path: str) -> list[dict]:
    if path.endswith(".jsonl"):
        rows = []
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows
    if path.endswith(".json"):
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, list):
            return payload
        return []

    rows = []
    with open(path, "r", encoding="utf-8") as handle:
        header = handle.readline().strip().split(",")
        handle.seek(0)
        if "company_ats_url" in header:
            import csv

            reader = csv.DictReader(handle)
            for row in reader:
                rows.append(row)
        else:
            import csv

            reader = csv.reader(handle)
            for row in reader:
                if row:
                    rows.append({"company_ats_url": row[0]})
    return rows
