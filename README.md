# URL Discovery Engine

Production URL discovery engine that verifies ATS job board URLs and discovers
company careers pages with strict/lenient modes and CSV outputs.

## Overview

This project resolves three input types:
- ATS root URLs -> company careers pages (direct).
- ATS job detail URLs -> ATS root -> company careers pages (breadcrumb).
- Corporate URLs -> careers page -> ATS board -> company careers pages (reverse).

Each resolution path validates HTTP responses, detects soft-404s and SSO redirects,
extracts company metadata, and writes append-only CSV output.

## Features

- ATS pattern matching and normalization for common providers.
- Strict/lenient modes with confidence labels.
- HTTP validation with per-domain rate limits.
- Soft-404 and SSO redirect detection.
- CSV outputs for resolved and unresolved records.

## Setup

Requires Python 3.11+.

```bash
cd /Users/sucharith/url_discovery_engine
pip install -e ".[dev]"
```

## CLI usage

You can use the Typer app module or the installed console script.

Resolve a single URL:

```bash
python -m src.cli resolve "https://boards.greenhouse.io/algolia"
```

Batch process a CSV (expects a column named `url` or a first-column URL list):

```bash
python -m src.cli batch input.csv --output output/output.csv --unresolved output/unresolved.csv
```

Careers resolver (ATS URL -> company domain + careers URL):

```bash
python -m src.cli careers-resolver input.csv --output output/careers_resolved.csv --debug output/careers_debug.jsonl
```

Console script (after install):

```bash
url-discovery resolve "https://boards.greenhouse.io/algolia"
```

### CLI options

`resolve`:
- `url`: Input URL (ATS or corporate).
- `mode`: `strict` or `lenient` (default: `strict`).
- `method`: `auto`, `direct`, `breadcrumb`, or `reverse` (default: `auto`).
- `output`: Output CSV path (default: `output/output.csv`).
- `unresolved`: Unresolved CSV path (default: `output/unresolved.csv`).

`batch`:
- `input_file`: CSV file with URLs.
- `mode`: `strict` or `lenient` (default: `strict`).
- `method`: `auto`, `direct`, `breadcrumb`, or `reverse` (default: `auto`).
- `output`: Output CSV path (default: `output/output.csv`).
- `unresolved`: Unresolved CSV path (default: `output/unresolved.csv`).
- `concurrency`: Concurrent tasks (default: `20`).

`careers-resolver`:
- `input_file`: CSV/JSON/JSONL with `company_ats_url` (+ optional `company_ats_name`, `master_company_domain`).
- `output`: CSV output path (default: `output/careers_resolved.csv`).
- `debug`: JSONL debug output path (default: `output/careers_debug.jsonl`).
- `concurrency`: Concurrent tasks (default: `5`).
- `--max-fetches-per-row`: Fetch budget per ATS URL (default: `4`).
- `--enable-sitemap-scan`: Enable sitemap recovery for PARTIAL rows (default: off).
- `--allow-homepage-fallback`: Allow homepage as `corporate_url` (default: off).
- `--export-resolved|--export-partial|--export-not-found|--export-all`: Filter CSV output.
- `--include-confidence-tier`: Append `confidence_tier` column to CSV.

### Resolution methods

- `direct`: ATS root URL -> validate -> extract careers URL -> validate.
- `breadcrumb`: ATS job URL -> normalize to ATS root -> direct flow.
- `reverse`: Corporate URL -> find careers -> discover ATS link.
- `auto`: Detects ATS patterns; uses `reverse` when the URL does not match ATS.

## Output format

Resolved CSV (`output/output.csv`) fields:

| field | description |
| --- | --- |
| company_ats_name | ATS platform identifier (GREENHOUSE, LEVER, etc.) |
| company_ats_url | Canonical ATS job board root URL |
| company_name_clean | Human-readable company name |
| company_domain | Root domain (e.g., `algolia.com`) |
| corporate_url | Company careers page URL |
| discovery_method | `direct`, `breadcrumb`, or `reverse` |
| confidence | `verified` or `inferred` |
| ats_status | HTTP status code for ATS URL |
| corporate_status | HTTP status code for corporate URL |
| verified_at | Verification timestamp |

Careers Resolver CSV (`output/careers_resolved.csv`) fields:

| field | description |
| --- | --- |
| company_ats_name | ATS platform identifier |
| company_ats_url | Canonical ATS job board root URL |
| company_name_clean | Human-readable company name |
| company_domain | Root domain (eTLD+1) |
| corporate_url | Careers/jobs URL only (blank if missing) |
| confidence_tier | Optional: HIGH/MEDIUM/NONE |

Careers Resolver debug JSONL (`output/careers_debug.jsonl`) includes status,
confidence, evidence sources, fetch log, ATS family expectations, and notes.

Unresolved CSV (`output/unresolved.csv`) fields:

| field | description |
| --- | --- |
| input_url | Original input URL |
| ats_name | Detected ATS platform (if any) |
| reason | Reason the record could not be resolved |
| attempted_at | Timestamp of the attempt |

Outputs are append-only. Delete the output files before a run if you want a
fresh dataset.

## Modes and confidence

- `strict`: Records are validated; missing company name or corporate careers URL
  are sent to the unresolved output.
- `lenient`: Records may include inferred careers URLs (common paths) and company
  names; `confidence` is downgraded to `inferred` when data is not fully verified.
  Records that still miss core fields are sent to the unresolved output.

## Careers Resolver governance

The Careers Resolver intentionally avoids inference and uses strict, observable
signals only. This means RESOLVED rates will differ by ATS family and are not
a direct measure of correctness.

- `RESOLVED`: Domain + real careers URL observed.
- `PARTIAL`: Domain observed, careers URL not found (expected for enterprise ATS).
- `NOT_FOUND`: ATS 404 or no corporate domain evidence.

The resolver will **never**:
- Guess careers paths or modify slugs.
- Use ATS URLs as corporate URLs.
- Accept social links as company domains.

ATS families are used only for reporting and expectation alignment, not for
resolution decisions.

## Configuration

Settings are loaded from environment variables via `pydantic-settings` (see `src/config.py`).
Common overrides:

- `MODE`: `strict` or `lenient`.
- `HTTP_TIMEOUT`: request timeout (seconds).
- `USER_AGENT`: outbound HTTP user agent.
- `DEFAULT_RATE_LIMIT`: requests per minute when no domain override is defined.

Rate limits and SSO/soft-404 heuristics are defined in `src/config.py`.

### Extending ATS detection

ATS detection can be extended by setting `ATS_DEFINITIONS_PATH` to a Python file
containing an `ATS_CATALOG` mapping. This is loaded at runtime by
`src/patterns/ats_patterns.py`. If the file does not exist or fails to import,
the external catalog is skipped.

## Development

Run tests:

```bash
pytest
```
