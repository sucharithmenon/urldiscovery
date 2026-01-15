# Extractors

Extractors parse HTML content to identify company metadata and URLs.

## Files
- `company_name.py`: extracts and normalizes company names from title, meta, JSON-LD, and headers.
- `corporate_url.py`: finds corporate/careers URLs from ATS pages using JSON-LD, link text, and ATS-specific patterns.
- `domain.py`: extracts public-suffix-aware domains and normalizes homepage URLs.
- `__init__.py`: package marker.
