"""Phase-2 ATS discovery and classification from careers URLs."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, urlunparse

from ..validators.http_validator import HTTPClient


ATS_DOMAIN_RULES = {
    "greenhouse": ["boards.greenhouse.io", "job-boards.greenhouse.io"],
    "lever": ["jobs.lever.co", "lever.co"],
    "ashby": ["jobs.ashbyhq.com"],
    "workable": ["apply.workable.com"],
    "workday": ["myworkdayjobs.com"],
    "smartrecruiters": ["careers.smartrecruiters.com", "smartrecruiters.com"],
}

ATS_HTML_MARKERS = {
    "greenhouse": ["greenhouse.io", "Greenhouse"],
    "lever": ["lever.co", "lever"],
    "ashby": ["ashbyhq"],
    "workable": ["workable"],
    "workday": ["workday"],
    "smartrecruiters": ["smartrecruiters"],
}

ATS_JS_MARKERS = {
    "greenhouse": ["greenhouse"],
    "lever": ["lever"],
    "ashby": ["ashby"],
    "workable": ["workable"],
    "workday": ["workday"],
    "smartrecruiters": ["smartrecruiters"],
}

ATS_API_MARKERS = {
    "greenhouse": ["boards-api.greenhouse.io"],
    "lever": ["lever.co/api", "api.lever.co"],
    "ashby": ["ashbyhq.com/api"],
    "workable": ["api.workable.com"],
    "workday": ["myworkdayjobs.com"],
    "smartrecruiters": ["api.smartrecruiters.com"],
}


@dataclass
class Phase2Result:
    company_name: str
    careers_url: str
    ats_provider: Optional[str]
    ats_base_url: Optional[str]
    confidence: str
    detection_signals: list[str]


class Phase2ATSResolver:
    def __init__(self, client: Optional[HTTPClient] = None, timeout: float = 12.0) -> None:
        self.client = client or HTTPClient()
        self.timeout = timeout

    async def resolve_one(self, company_name: str, careers_url: str) -> Phase2Result:
        if not careers_url:
            return Phase2Result(company_name, careers_url, None, None, "low", [])

        validation, html = await self.client.fetch_and_validate(careers_url)
        final_url = validation.final_url or careers_url
        signals = []
        provider = self._detect_provider(final_url, html, signals)

        if not provider:
            return Phase2Result(company_name, careers_url, None, None, "low", signals)

        ats_base_url = self._normalize_base_url(provider, final_url, html)
        confidence = self._confidence(provider, signals)
        return Phase2Result(company_name, careers_url, provider, ats_base_url, confidence, signals)

    async def resolve_batch(self, inputs: list[dict], concurrency: int = 10) -> list[Phase2Result]:
        semaphore = asyncio.Semaphore(concurrency)

        async def run_one(row: dict) -> Phase2Result:
            async with semaphore:
                return await self.resolve_one(
                    company_name=row.get("company_name", ""),
                    careers_url=row.get("careers_url", ""),
                )

        tasks = [asyncio.create_task(run_one(row)) for row in inputs]
        return await asyncio.gather(*tasks)

    def _detect_provider(self, final_url: str, html: str, signals: list[str]) -> Optional[str]:
        host = urlparse(final_url).netloc.lower()
        provider_from_domain = None
        for provider, domains in ATS_DOMAIN_RULES.items():
            if any(host.endswith(domain) for domain in domains):
                signals.append("final_hostname")
                provider_from_domain = provider
                break

        provider_from_html = self._find_marker(html, ATS_HTML_MARKERS, signals, "html_marker")
        provider_from_js = self._find_marker(html, ATS_JS_MARKERS, signals, "js_bundle")
        provider_from_api = self._find_marker(html, ATS_API_MARKERS, signals, "network_call")

        if provider_from_domain:
            return provider_from_domain

        markers = [provider_from_html, provider_from_js, provider_from_api]
        markers = [provider for provider in markers if provider]
        if not markers:
            return None
        if len(set(markers)) == 1 and provider_from_api:
            return provider_from_api
        return None

    def _find_marker(self, html: str, markers: dict, signals: list[str], label: str) -> Optional[str]:
        if not html:
            return None
        lowered = html.lower()
        for provider, patterns in markers.items():
            for pattern in patterns:
                if pattern in lowered:
                    signals.append(label)
                    return provider
        return None

    def _normalize_base_url(self, provider: str, final_url: str, html: str) -> Optional[str]:
        parsed = urlparse(final_url)
        host = parsed.netloc
        path_parts = [p for p in parsed.path.split("/") if p]
        if provider == "greenhouse" and path_parts:
            return f"https://{host}/{path_parts[0]}"
        if provider == "lever" and path_parts:
            return f"https://{host}/{path_parts[0]}"
        if provider == "ashby" and path_parts:
            return f"https://{host}/{path_parts[0]}"
        if provider == "workable" and len(path_parts) >= 1:
            return f"https://{host}/{path_parts[0]}"
        if provider == "smartrecruiters" and len(path_parts) >= 1:
            return f"https://{host}/{path_parts[0]}"
        if provider == "workday":
            if len(path_parts) >= 1:
                return f"https://{host}/{path_parts[0]}"
            return f"https://{host}{parsed.path}"
        return f"https://{host}{parsed.path}" if host else None

    def _confidence(self, provider: str, signals: list[str]) -> str:
        if "final_hostname" in signals and ("html_marker" in signals or "js_bundle" in signals or "network_call" in signals):
            return "high"
        if "final_hostname" in signals:
            return "medium"
        return "low"


def load_phase2_inputs(path: str) -> list[dict]:
    rows = []
    if path.endswith(".jsonl"):
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                if payload.get("careers_url"):
                    rows.append(payload)
        return rows

    with open(path, "r", encoding="utf-8") as handle:
        header = handle.readline().strip().split(",")
        handle.seek(0)
        if "careers_url" in header:
            import csv

            reader = csv.DictReader(handle)
            for row in reader:
                if row.get("careers_url"):
                    rows.append(row)
        else:
            import csv

            reader = csv.reader(handle)
            for row in reader:
                if row and row[0]:
                    rows.append({"company_name": "", "careers_url": row[0]})
    return rows
