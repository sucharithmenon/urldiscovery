# urldiscovery

Production URL discovery engine that verifies ATS job board URLs and corporate careers pages with strict/lenient modes and CSV outputs.

## Setup

```bash
cd /Users/sucharith/url_discovery_engine
pip install -e "[.dev]"
```

## Usage

Resolve a single URL:

```bash
python -m src.cli resolve "https://boards.greenhouse.io/algolia"
```

Batch process a CSV (expects a column named `url`):

```bash
python -m src.cli batch input.csv --output output/output.csv --unresolved output/unresolved.csv
```

## Output

- `output/output.csv`: verified records
- `output/unresolved.csv`: records that failed strict validation
