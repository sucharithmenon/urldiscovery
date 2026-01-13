"""CSV writer utilities."""

from __future__ import annotations

import csv
from pathlib import Path

from ..models import CompanyRecord, CSV_FIELDS


def append_company_record(path: str, record: CompanyRecord) -> None:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(record.to_csv_row())
