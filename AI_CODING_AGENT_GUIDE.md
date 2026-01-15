# AI Coding Agent Guide: URL Discovery Engine

This comprehensive guide helps AI agents (Claude, GPT, etc.) work effectively with the URL Discovery Engine codebase. Focus on practical patterns, specific commands, and actionable guidance.

## 1. Project Structure Overview

### Core Source Code (`src/`)
- **`cli.py`** - Main CLI entry point with all commands
- **`models.py`** - Pydantic data models (CompanyRecord, UnresolvedRecord)
- **`config.py`** - Settings and configuration patterns
- **`patterns/`** - ATS detection and URL pattern matching
- **`resolvers/`** - Core resolution logic (direct, breadcrumb, reverse)
- **`extractors/`** - HTML parsing for company names and corporate URLs
- **`validators/`** - HTTP validation and content checking
- **`output/`** - CSV writing and run tracking
- **`utils/`** - Logging and utility functions

### Important Files vs. Ignorable Files
**WORK WITH THESE:**
- All `src/` Python files
- `pyproject.toml` - Dependencies and project config
- `tests/` - Test files for understanding expected behavior
- `docs/PROJECT_CONTEXT.md` - High-level project understanding

**IGNORE THESE (generated/ephemeral):**
- `output/` - Generated CSV files (unless debugging specific runs)
- `runs/` - Run tracking data
- `*.log` - Debug logs
- `demo_*.csv`, `test_*.csv` - Test data files
- `*.sh` - Deployment scripts (unless working on deployment)

## 2. Development Workflow

### Environment Setup
```bash
# Install in development mode
cd /Users/sucharith/url_discovery_engine
pip install -e ".[dev]"

# Verify installation
python -m src.cli --help
```

### Testing Strategy
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_extractors.py

# Run with coverage
pytest --cov=src
```

### Making Changes
1. **Always read existing files first** to understand patterns
2. **Run tests before and after** changes to verify behavior
3. **Use verbose mode** for debugging: `--verbose/-v` flag
4. **Test with small datasets** first using `--limit` flag

## 3. Code Architecture

### Core Resolution Flow
All resolution follows this pattern:
1. **Detection** - `patterns/ats_patterns.py:detect()` identifies ATS type
2. **Normalization** - `patterns/ats_patterns.py:normalize()` creates canonical URLs
3. **Validation** - `validators/http_validator.py:HTTPClient.validate()` checks HTTP status
4. **Extraction** - `extractors/` pull company data from HTML
5. **Resolution** - `resolvers/` orchestrate the flow and return CompanyRecord/UnresolvedRecord

### Key Data Models (`src/models.py`)
```python
# Success output
CompanyRecord(
    company_ats_name="GREENHOUSE",
    company_ats_url="https://boards.greenhouse.io/algolia",
    company_name_clean="Algolia",
    company_domain="algolia.com",
    corporate_url="https://www.algolia.com/careers",
    discovery_method="direct",
    confidence="verified"
)

# Failure output
UnresolvedRecord(
    input_url="https://boards.greenhouse.io/invalid",
    ats_name="GREENHOUSE",
    reason="HTTP 404",
    error_category="http_error",
    http_status=404
)
```

### Resolution Types
- **Direct**: ATS root URL → extract careers URL → validate
- **Breadcrumb**: ATS job URL → normalize to ATS root → direct flow
- **Reverse**: Corporate URL → find careers → discover ATS link
- **Auto**: Detects ATS patterns; uses reverse when no ATS match

## 4. Build & Deployment

### Local Development
```bash
# Single URL resolution
python -m src.cli resolve "https://boards.greenhouse.io/algolia" --verbose

# Batch processing with limits
python -m src.cli batch input.csv --limit 10 --verbose --progress-every 1
```

### Production Commands
```bash
# Full batch processing
python -m src.cli batch input.csv \
  --output output/validated.csv \
  --unresolved output/unresolved.csv \
  --mode strict \
  --concurrency 20

# QA workflow for fixing failures
python -m src.cli qa-export output/unresolved.csv output/qa_template.csv
# (manually edit qa_template.csv)
python -m src.cli qa-apply output/qa_template.csv
```

### Configuration
Environment variables in `src/config.py`:
- `MODE`: `strict` or `lenient`
- `HTTP_TIMEOUT`: Request timeout
- `DEFAULT_RATE_LIMIT`: Per-domain rate limiting
- `USER_AGENT`: HTTP user agent string

## 5. Common Tasks

### Adding New ATS Patterns
1. **Edit `src/patterns/ats_patterns.py`**
2. **Add to PATTERNS list:**
```python
ATSPattern(
    name="NEW_ATS",
    root_regex=re.compile(r"https?://ats\.example\.com/(?P<slug>[^/?#]+)/?", re.IGNORECASE),
    job_regex=re.compile(r"https?://ats\.example\.com/(?P<slug>[^/?#]+)/job/[^/?#]+", re.IGNORECASE),
    root_template="https://ats.example.com/{slug}",
)
```
3. **Add to USER_ATS_NAMES set**
4. **Add tests in `tests/test_extractors.py`**

### Fixing Validation Issues
1. **Check HTTP validation in `src/validators/http_validator.py`**
2. **Review soft-404 patterns in `src/config.py`**
3. **Add domain patterns for SSO detection:**
```python
SSO_REDIRECT_DOMAINS = [
    "sso.example.com",  # Add new SSO domains
    "login.example.com",
]
```

### Updating Extractors
**Company name extraction (`src/extractors/company_name.py`):**
```python
def extract(html: str, slug: str, mode: str) -> str:
    # Add new patterns for title cleanup
    title_patterns = [
        r"^(.*?)\s+\|\s+Careers?$",
        r"^(.*?)\s+-\s+Career Page$",  # Add new patterns here
    ]
```

**Corporate URL extraction (`src/extractors/corporate_url.py`):**
```python
# Add new selectors for finding careers links
CAREERS_SELECTORS = [
    "a[href*='careers']",
    "a[href*='jobs']",  # Add new selectors
]
```

### Debugging Failed Resolutions
1. **Use verbose mode:** `--verbose` flag creates debug logs
2. **Check validation signals** in UnresolvedRecord
3. **Review HTTP status and redirect chains**
4. **Test individual components:**
```python
# Test detection
from src.patterns.ats_patterns import detect
print(detect("https://boards.greenhouse.io/algolia"))

# Test validation
from src.validators.http_validator import HTTPClient
client = HTTPClient()
result = await client.validate("https://example.com")
```

## 6. Debugging & Troubleshooting

### Enhanced Debugging Features
The codebase includes comprehensive debugging capabilities:

**Verbose Logging:**
```bash
# Enable detailed debug output
python -m src.cli resolve "https://example.com" --verbose

# Creates timestamped debug logs with:
# - HTTP request details
# - Validation failure signals
# - Extraction attempts
# - Redirect chains
```

**Debug Information Available:**
- **Validation signals**: Specific reasons why validation failed
- **HTTP details**: Status codes, final URLs, redirect chains
- **Error categories**: `http_error`, `validation_error`, `extraction_error`
- **Fetch counts**: Number of HTTP requests made per resolution

### Common Issues and Solutions

**Soft 404 Detection:**
```python
# Add new soft-404 patterns in src/config.py
SOFT_404_PATTERNS = [
    r"page\s*not\s*found",
    r"no\s*jobs?\s*(found|available)",  # Add new patterns
]
```

**Rate Limiting:**
```python
# Adjust per-domain limits in src/config.py
RATE_LIMITS = {
    "greenhouse.io": 30,  # Increase/decrease as needed
    "lever.co": 30,
}
```

**Corporate URL Validation:**
```python
# Update vendor domain blacklist in src/extractors/corporate_url.py
VENDOR_DOMAINS = {
    "greenhouse.io",
    "lever.co",
    # Add new ATS domains to exclude
}
```

### Testing Individual Components
```python
# Test ATS detection
from src.patterns.ats_patterns import detect, normalize
url = "https://boards.greenhouse.io/algolia/jobs/123"
print(detect(url))  # Should return ("GREENHOUSE", "algolia")
print(normalize(url))  # Should return root URL

# Test company name extraction
from src.extractors.company_name import extract
html = "<title>Acme Corp - Careers</title>"
print(extract(html, "acme", "strict"))  # Should return "Acme Corp"

# Test HTTP validation
from src.validators.http_validator import HTTPClient
client = HTTPClient()
result = await client.validate("https://example.com")
print(f"Status: {result.status_code}, Soft 404: {result.is_soft_404}")
```

## 7. Best Practices

### Code Style and Patterns
1. **Follow existing patterns** - Don't invent new approaches
2. **Use Pydantic models** for all data structures
3. **Async/await** for all HTTP operations
4. **Type hints** required for all functions
5. **Error handling** with UnresolvedRecord, not exceptions

### Testing Strategy
1. **Write tests for new patterns** in `tests/test_extractors.py`
2. **Test both success and failure cases**
3. **Use small, focused test functions**
4. **Mock HTTP requests** for deterministic tests

### Performance Considerations
1. **Respect rate limits** - Don't increase beyond what servers can handle
2. **Use connection pooling** via HTTPClient
3. **Limit concurrent requests** with semaphore
4. **Cache HTTP responses** where appropriate

### Adding New Features
1. **Start with tests** to define expected behavior
2. **Implement incrementally** - Small, testable changes
3. **Update documentation** in CLI help strings
4. **Consider backward compatibility** for CSV outputs

### Working with CSV Architecture
The system uses append-only CSV architecture for scalability:
- **Never modify existing records** - Always append new ones
- **Use deduplication** sparingly and explicitly (`--dedupe` flag)
- **Field order matters** - Maintain CSV_FIELDS order in `models.py`
- **Handle missing data** gracefully with empty strings

### Debug Workflow
1. **Start with small dataset** using `--limit 10`
2. **Enable verbose logging** with `--verbose`
3. **Check debug logs** for validation signals and HTTP details
4. **Use qa-export** to manually review failures
5. **Iterate on patterns** based on real-world examples

## 8. Quick Reference Commands

```bash
# Development
pip install -e ".[dev]"
pytest

# Single URL testing
python -m src.cli resolve "URL" --verbose

# Batch processing
python -m src.cli batch input.csv --limit 100 --verbose

# QA workflow
python -m src.cli qa-export output/unresolved.csv output/qa.csv
python -m src.cli qa-apply output/qa.csv

# Careers URL resolution
python -m src.cli careers-resolver input.csv --limit 50
```

## 9. File Pattern Reference

| Task | File(s) | Key Functions |
|------|---------|---------------|
| ATS Detection | `src/patterns/ats_patterns.py` | `detect()`, `normalize()` |
| Company Names | `src/extractors/company_name.py` | `extract()` |
| Corporate URLs | `src/extractors/corporate_url.py` | `extract()` |
| HTTP Validation | `src/validators/http_validator.py` | `HTTPClient.validate()` |
| Direct Resolution | `src/resolvers/direct_resolver.py` | `DirectResolver.resolve()` |
| CLI Commands | `src/cli.py` | `resolve()`, `batch()` |
| Configuration | `src/config.py` | Settings, rate limits, patterns |

This guide should help AI agents work effectively with the codebase while maintaining consistency and reliability.