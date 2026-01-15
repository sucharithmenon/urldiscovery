# Validators

Validators handle HTTP validation and ATS root page checks.

## Files
- `http_validator.py`: async HTTP client with rate limiting, soft-404 detection, and SSO redirect detection.
- `ats_root_validator.py`: validates ATS root pages by confirming scope, job listings, and empty-state signals.
- `__init__.py`: package marker.
