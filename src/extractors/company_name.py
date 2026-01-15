"""Company name extraction from ATS HTML."""

from __future__ import annotations

import json
import re
from typing import Iterable, Optional

from bs4 import BeautifulSoup


_PREFIXES = [
    re.compile(r"^careers?\s*(at|@)\s*", re.IGNORECASE),
    re.compile(r"^jobs?\s*(at|@)\s*", re.IGNORECASE),
    re.compile(r"^join\s*", re.IGNORECASE),
    re.compile(r"^work\s*(at|with)\s*", re.IGNORECASE),
    re.compile(r"^(current\s+openings?|open\s+positions?|job\s+openings?|search\s+jobs?)\s*[-|:]\s*", re.IGNORECASE),
]

_SUFFIXES = [
    re.compile(r"\s*[-|]\s*careers?$", re.IGNORECASE),
    re.compile(r"\s*[-|]\s*jobs?$", re.IGNORECASE),
    re.compile(r"\s*[-|]\s*hiring$", re.IGNORECASE),
    re.compile(r"\s*[-|:]\s*(inactive\s*)?career page$", re.IGNORECASE),
    re.compile(r"\s*[-|:]\s*(current\s+openings?|open\s+positions?|job\s+openings?)$", re.IGNORECASE),
    re.compile(r"\s*[-|:]\s*(career|job)\s+opportunities$", re.IGNORECASE),
    re.compile(r"\s*careers?$", re.IGNORECASE),
    re.compile(r"\s*jobs?$", re.IGNORECASE),
]

_LEGAL_SUFFIXES = [
    re.compile(
        r"\s*,?\s*(incorporated|inc\.?|llc|l\.l\.c\.|ltd\.?|limited|corp\.?|corporation|co\.?|company)\.?$",
        re.IGNORECASE,
    ),
    re.compile(r"\s*,?\s*(gmbh|ag|bv|ab|nv|plc|llp)\.?$", re.IGNORECASE),
    re.compile(r"\s*,?\s*(oy|oyj)\.?$", re.IGNORECASE),
    re.compile(r"\s*,?\s*(pte\.?\s*ltd\.?|pvt\.?\s*ltd\.?)$", re.IGNORECASE),
    re.compile(r"\s*,?\s*(s\.?a\.?s\.?|s\.?a\.?|s\.?r\.?l\.?|srl|spa)$", re.IGNORECASE),
]


def _clean_name(name: str) -> str:
    if not name:
        return ""
    cleaned = " ".join(name.split())
    for pattern in _PREFIXES:
        cleaned = pattern.sub("", cleaned)
    for pattern in _SUFFIXES:
        cleaned = pattern.sub("", cleaned)
    for pattern in _LEGAL_SUFFIXES:
        cleaned = pattern.sub("", cleaned)
    return cleaned.strip(" -|")


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


def _extract_org_name(obj: dict) -> str | None:
    types = obj.get("@type")
    if isinstance(types, list):
        type_list = [t.lower() for t in types if isinstance(t, str)]
    elif isinstance(types, str):
        type_list = [types.lower()]
    else:
        type_list = []
    if "organization" not in type_list:
        return None
    name = obj.get("name")
    if isinstance(name, str):
        return name
    return None


def _slug_to_name(slug: str) -> str:
    if not slug:
        return ""
    return slug.replace("-", " ").replace("_", " ").title()


def clean_company_name(name: str) -> str:
    return _clean_name(name)


def slug_to_company_name(slug: str) -> str:
    return _clean_name(_slug_to_name(slug))


def extract(html: str, slug: Optional[str] = None, mode: str = "strict") -> Optional[str]:
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    og = soup.find("meta", attrs={"property": "og:site_name"})
    if og and og.get("content"):
        cleaned = _clean_name(og["content"])
        if cleaned:
            return cleaned

    if soup.title and soup.title.string:
        cleaned = _clean_name(soup.title.string)
        if cleaned:
            return cleaned

    for obj in _iter_json_ld_objects(soup):
        name = _extract_org_name(obj)
        if name:
            cleaned = _clean_name(name)
            if cleaned:
                return cleaned

    h1 = soup.find("h1")
    if h1:
        cleaned = _clean_name(h1.get_text(" ", strip=True))
        if cleaned:
            return cleaned

    if mode == "lenient" and slug:
        cleaned = _slug_to_name(slug)
        if cleaned:
            return cleaned

    return None
