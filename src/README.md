# src Package Overview

This package contains the core URL Discovery Engine logic. The CLI in `src/cli.py` coordinates the pipeline. Resolvers and extractors are organized by responsibility.

## Key Modules
- `cli.py`: CLI entry points and batch orchestration.
- `config.py`: runtime settings, rate limits, and HTTP configuration.
- `models.py`: Pydantic models for resolved and unresolved records.
- `utils/logging.py`: debug logging helpers for HTTP and validation signals.

## Subpackages
- `resolvers/`: resolution strategies for ATS and corporate URLs.
- `extractors/`: HTML parsing helpers for company name and corporate URLs.
- `patterns/`: ATS detection and careers indicator rules.
- `validators/`: HTTP validation and ATS root validation.
- `output/`: CSV writers and run tracking.
