# Project context

## Purpose
The URL Discovery Engine normalizes and validates Applicant Tracking System (ATS)
job board URLs (strict or lenient modes) and attempts to resolve the matching
corporate careers page. The CLI supports single URL resolution or batch CSV
processing.

## Repository layout

- `src/cli.py`: CLI entry points for resolving and batch processing URLs.
- `src/patterns/`: ATS pattern detection and normalization logic.
- `src/extractors/`: HTML parsing helpers for company name and corporate URL
  extraction.
- `src/resolvers/`: High-level resolution logic orchestrating extractors and
  validators.
- `src/validators/`: Validation and URL checking utilities.
- `src/output/`: CSV output formatting helpers.
- `tests/`: Pytest coverage for patterns and extractors.

## Development setup

```bash
python -m pip install -e ".[dev]"
```

## Running tests

```bash
pytest
```

The tests import the `src` package directly. When running tests from the
repository root, `tests/conftest.py` ensures the root directory is on
`sys.path` so the package is importable without requiring installation.
