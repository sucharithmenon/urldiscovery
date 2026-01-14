"""CSV writer utilities."""

from __future__ import annotations

import csv
from pathlib import Path

from ..models import CompanyRecord, CSV_FIELDS


_DEDUP_KEY_FIELDS = ("company_ats_name", "company_ats_url")
_DEDUP_FIELD_WEIGHTS = {
    "company_name_clean": 1,
    "company_domain": 1,
    "corporate_url": 2,
}


def append_company_record(path: str, record: CompanyRecord) -> None:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(record.to_csv_row())


def _row_key(row: dict) -> str:
    ats_name = (row.get("company_ats_name") or "").strip().upper()
    ats_url = (row.get("company_ats_url") or "").strip().lower()
    return f"{ats_name}|{ats_url}"


def _row_score(row: dict) -> int:
    score = 0
    for field, weight in _DEDUP_FIELD_WEIGHTS.items():
        value = row.get(field)
        if value:
            score += weight
    return score


def _prefer_candidate(existing: dict | None, candidate: dict) -> bool:
    if existing is None:
        return True
    candidate_score = _row_score(candidate)
    existing_score = _row_score(existing)
    if candidate_score > existing_score:
        return True
    if candidate_score < existing_score:
        return False
    if candidate.get("corporate_url") and not existing.get("corporate_url"):
        return True
    return False


def dedupe_company_file(path: str) -> None:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
            writer.writerow(record.to_csv_row())
    else:
        # Existing file - find duplicate entries before appending
        if rows and any(field in rows[0] for field in ["error_category", "validation_signals"]):
            fieldnames = UNRESOLVED_CSV_FIELDS
        elif rows and "company_ats_url" in rows[0]:
            fieldnames = QA_EXPORT_FIELDS
        else:
            fieldnames = CSV_FIELDS  # ALWAYS use the enhanced field list
        with csv_path.open("r", newline="", encoding="utf-8") as read_handle:
            reader = csv.DictReader(read_handle)
            seen = set()
            for row in reader:
                key = _row_key(row)
                if key in seen:
                    # Duplicate found
                    break
                seen.add(key)
            
            # Calculate counts for progress reporting
            validated_count = sum(1 for row in reader if "ats_name" in row and row["ats_name"] != "")
            unresolved_count = reader.line_num - 1 - validated_count
            seen_count = len(seen)
            
            if seen_count > 0:
                # Duplicates detected - skip deduplication for now
                with csv_path.open("a", newline="", encoding="utf-8") as write_handle:
                    writer = csv.DictWriter(write_handle, fieldnames=CSV_FIELDS)
                    writer.writeheader()
                    for row in reader:
                        writer.writerow(row)
            else:
                # No duplicates - simply copy all records
                with csv_path.open("a", newline="", encoding="utf-8") as write_handle:
                    writer = csv.DictWriter(write_handle, fieldnames=CSV_FIELDS)
                    writer.writeheader()
                    for row in reader:
                        writer.writerow(row)
    tmp_path.replace(csv_path)
