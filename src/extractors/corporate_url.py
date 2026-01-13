"""Extract corporate careers URL from ATS HTML."""

from __future__ import annotations

import json
from typing import Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import ExtractionResult
from ..patterns.careers_indicators import has_careers_indicator, has_careers_text


def _iter_json_ld_objects(soup: BeautifulSoup) -> Iterable[dict]:
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    yield item
        elif isinstance(data, dict):
            if "@graph" in data and isinstance(data["@graph"], list):
                for item in data["@graph"]:
                    if isinstance(item, dict):
                        yield item
            else:
                yield data


def _extract_org_urls(obj: dict) -> list[str]:
    types = obj.get("@type")
    if isinstance(types, list):
        type_list = [t.lower() for t in types if isinstance(t, str)]
    elif isinstance(types, str):
        type_list = [types.lower()]
    else:
        type_list = []
    if "organization" not in type_list:
        return []
    urls = []
    if isinstance(obj.get("url"), str):
        urls.append(obj["url"])
    same_as = obj.get("sameAs")
    if isinstance(same_as, list):
        urls.extend([u for u in same_as if isinstance(u, str)])
    elif isinstance(same_as, str):
        urls.append(same_as)
    return urls


def _filter_http(urls: Iterable[str]) -> list[str]:
    out = []
    for url in urls:
        if not url:
            continue
        cleaned = url.strip()
        if cleaned.startswith("http://") or cleaned.startswith("https://"):
            out.append(cleaned)
    return out


def extract(html: str, base_url: str) -> ExtractionResult | None:
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    inferred_candidates: list[ExtractionResult] = []

    # JSON-LD
    for obj in _iter_json_ld_objects(soup):
        for url in _filter_http(_extract_org_urls(obj)):
            if has_careers_indicator(url):
                return ExtractionResult(value=url, source="json-ld", confidence="verified")
            inferred_candidates.append(
                ExtractionResult(value=url, source="json-ld", confidence="inferred")
            )

    # Meta tags
    for meta in soup.find_all("meta"):
        prop = (meta.get("property") or "").lower()
        if prop not in {"og:see_also"}:
            continue
        url = meta.get("content")
        if not url:
            continue
        if has_careers_indicator(url):
            return ExtractionResult(value=url, source="meta", confidence="verified")
        inferred_candidates.append(
            ExtractionResult(value=url, source="meta", confidence="inferred")
        )

    # Links with careers indicators
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        full = urljoin(base_url, href)
        if has_careers_indicator(full):
            return ExtractionResult(value=full, source="link", confidence="verified")

    # Links with careers text
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        full = urljoin(base_url, href)
        text = link.get_text(" ", strip=True)
        if has_careers_text(text):
            if has_careers_indicator(full):
                return ExtractionResult(value=full, source="link-text", confidence="verified")
            inferred_candidates.append(
                ExtractionResult(value=full, source="link-text", confidence="inferred")
            )

    # Logo/header links
    for link in soup.find_all("a", href=True):
        classes = " ".join(link.get("class", [])).lower()
        if "logo" in classes or "brand" in classes:
            full = urljoin(base_url, link.get("href", ""))
            inferred_candidates.append(
                ExtractionResult(value=full, source="logo", confidence="inferred")
            )

    if inferred_candidates:
        return inferred_candidates[0]

    return None
