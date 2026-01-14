"""PSL-aware domain extraction."""

from __future__ import annotations

from urllib.parse import urlparse

import tldextract


_TLD_EXTRACT = tldextract.TLDExtract(
    suffix_list_urls=None,
    cache_dir=".tldextract-cache",
)


def extract_domain(url: str) -> str | None:
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if not parsed.netloc:
        return None
    result = _TLD_EXTRACT(parsed.netloc)
    if result.domain and result.suffix:
        return f"{result.domain}.{result.suffix}"
    return None


def extract_homepage(url: str) -> str | None:
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"
