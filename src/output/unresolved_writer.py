"""CSV writer for unresolved records."""

from __future__ import annotations

import csv
from pathlib import Path

from ..models import UNRESOLVED_CSV_FIELDS, UnresolvedRecord


def append_unresolved_record(path: str, record: UnresolvedRecord) -> None:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=UNRESOLVED_CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(record.to_csv_row())
