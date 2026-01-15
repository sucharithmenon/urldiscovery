# Opencode Architecture Overview

This document describes the URL Discovery Engine logic (code-only). It intentionally excludes runtime data files, logs, and generated outputs.

## Purpose
The engine resolves company metadata from URLs that reference ATS platforms or company sites. It produces either:
- `CompanyRecord`: verified/inferred ATS + corporate metadata.
- `UnresolvedRecord`: failure reason, HTTP status, and signals for analysis.

## High-Level Flow
1. Input URL(s) enter the CLI (`src/cli.py`).
2. The CLI selects a resolver strategy (`direct`, `breadcrumb`, or `reverse`).
3. Resolvers validate HTTP responses and parse HTML using extractors.
4. Patterns classify ATS platforms and normalize root URLs.
5. Output writers persist resolved and unresolved records.

## Core Data Models
Defined in `src/models.py`:
- `CompanyRecord`: ATS name/URL, company name, domain, corporate URL, status codes, discovery method, and confidence.
- `UnresolvedRecord`: input URL, ATS name (if detected), reason, error category, HTTP status, final URL, and validation signals.
- `ValidationResult`: HTTP result with redirect and soft-404 signals.
- `ExtractionResult`: value + source metadata for HTML extraction.

## Resolver Strategies
All resolvers rely on the shared `HTTPClient`, ATS pattern detection, and extractors.

### Direct Resolver (ATS URL → corporate URL)
`src/resolvers/direct_resolver.py`
- Detects ATS provider from the input URL.
- Normalizes to the ATS root URL and validates it.
- Extracts corporate/careers URLs from ATS HTML (JSON-LD, links, scripts).
- Falls back to job detail pages when corporate URLs are missing.
- Validates corporate URLs; produces a `CompanyRecord` or `UnresolvedRecord`.

### Breadcrumb Resolver (Job URL → ATS root → direct)
`src/resolvers/breadcrumb_resolver.py`
- Accepts job detail URLs.
- Normalizes them to the ATS root.
- Deduplicates roots per run.
- Delegates to `DirectResolver`.

### Reverse Resolver (Corporate URL → ATS URL)
`src/resolvers/reverse_resolver.py`
- Starts from a corporate homepage.
- Searches for ATS links or iframes.
- If missing, discovers a careers page via link text or common paths.
- Scrapes job detail pages to find ATS links.
- Builds a `CompanyRecord` with discovery method `reverse`.

### Careers Resolver (ATS URL → corporate URL)
`src/resolvers/careers_resolver.py`
- Specialized ATS-root resolver to discover corporate domains and careers pages.
- Scores candidate links from ATS HTML (header/footer/logo/link text).
- Can optionally scan corporate homepages or sitemaps.
- Emits debug info for status, evidence, and fetch logs.

### Phase 1/2 Discovery Pipeline
- `src/resolvers/phase1_careers_resolver.py`: crawl company sites to find careers URLs while respecting robots.txt.
- `src/resolvers/phase2_ats_resolver.py`: classify ATS provider from careers pages using domain, HTML, JS, and API markers.

## Pattern Detection
Patterns live in `src/patterns/`:
- `ats_patterns.py`: canonical ATS URL detection, normalization, and registry-backed rules.
- `registry_patterns.py`: long-tail ATS regex catalog.
- `ats_fingerprints.py`: HTML fingerprint detection for ATS hints.
- `careers_indicators.py`: common URL paths and text cues for careers pages.

## Extractors
Extractors live in `src/extractors/`:
- `company_name.py`: company name extraction from HTML title, meta, JSON-LD, and h1.
- `corporate_url.py`: corporate/careers URL extraction with ATS-specific heuristics.
- `domain.py`: public suffix aware domain extraction and homepage normalization.

## Validators and Networking
Validators live in `src/validators/`:
- `http_validator.py`: async HTTP client with per-domain rate limits, soft-404 detection, and SSO redirect checks.
- `ats_root_validator.py`: validates ATS root pages by confirming scope and job listing signals.

## Output Writers
Output utilities live in `src/output/`:
- `csv_writer.py`: writes and deduplicates validated company records.
- `unresolved_writer.py`: writes unresolved records with diagnostics.
- `run_tracker.py`: tracks batch metadata, progress, and summary statistics.

## CLI Entry Points
`src/cli.py` provides the main operational surface:
- `resolve`: resolve a single URL.
- `batch`: resolve a CSV of URLs concurrently.
- `qa-export`: export unresolved items for manual review.
- `company-suggestions`: generate company name/domain suggestions for QA.
- `qa-apply`: apply manual fixes and re-validate.
- `careers-resolver`: ATS → corporate URL resolution with debug output.
- `phase1-careers` and `phase2-ats`: two-stage discovery pipeline.

## Configuration
`src/config.py` defines:
- rate limits, HTTP timeout, user agent, and soft-404 patterns
- a `Settings` model for environment-based overrides

## Change Control
All logic changes should update:
- `docs/OPENCODE_ARCHITECTURE.md` (this file)
- `docs/OPENCODE_CHANGELOG.md` (append an entry)
