"""Run tracking utilities for validation batches."""

from __future__ import annotations

import csv
import hashlib
import json
import secrets
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


INDEX_FIELDS = [
    "run_id",
    "started_at",
    "completed_at",
    "input_file",
    "input_hash",
    "validated_count",
    "unresolved_count",
    "status",
    "top_reason",
]


@dataclass(frozen=True)
class RunContext:
    run_id: str
    run_dir: Path
    output_path: Path
    unresolved_path: Path
    input_path: Optional[Path]
    input_hash: str
    started_at: str
    run_output_path: Path
    run_unresolved_path: Path
    input_snapshot_path: Optional[Path]
    summary_path: Path
    progress_path: Path
    index_path: Path


def _hash_file(path: Path) -> str:
    if not path.exists():
        return ""
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def create_run_context(
    run_root: str,
    output_path: str,
    unresolved_path: str,
    input_file: Optional[str] = None,
    snapshot_input: bool = True,
) -> RunContext:
    now = datetime.utcnow()
    run_id = f"{now:%Y%m%d-%H%M%S}_{secrets.token_hex(3)}"
    run_dir = Path(run_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(input_file) if input_file else None
    input_hash = _hash_file(input_path) if input_path else ""
    input_snapshot_path = None
    if input_path and input_path.exists() and snapshot_input:
        input_snapshot_path = run_dir / "input_snapshot.csv"
        shutil.copy2(input_path, input_snapshot_path)

    return RunContext(
        run_id=run_id,
        run_dir=run_dir,
        output_path=Path(output_path),
        unresolved_path=Path(unresolved_path),
        input_path=input_path,
        input_hash=input_hash,
        started_at=now.isoformat(),
        run_output_path=run_dir / "validated.csv",
        run_unresolved_path=run_dir / "unresolved.csv",
        input_snapshot_path=input_snapshot_path,
        summary_path=run_dir / "summary.json",
        progress_path=run_dir / "progress.json",
        index_path=Path(run_root) / "index.csv",
    )


def _count_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return max(0, sum(1 for _ in handle) - 1)


def _top_reasons(path: Path, limit: int = 5) -> list[dict]:
    if not path.exists():
        return []
    reasons = Counter()
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            reason = (row.get("reason") or "").strip()
            if reason:
                reasons[reason] += 1
    return [{"reason": reason, "count": count} for reason, count in reasons.most_common(limit)]


def finalize_run(context: RunContext) -> None:
    validated_count = _count_rows(context.output_path)
    unresolved_count = _count_rows(context.unresolved_path)

    if context.output_path.exists():
        shutil.copy2(context.output_path, context.run_output_path)
    if context.unresolved_path.exists():
        shutil.copy2(context.unresolved_path, context.run_unresolved_path)

    completed_at = datetime.utcnow().isoformat()
    top_reasons = _top_reasons(context.unresolved_path, limit=5)
    status = "complete" if (validated_count or unresolved_count) else "empty"
    top_reason = top_reasons[0]["reason"] if top_reasons else ""

    summary = {
        "run_id": context.run_id,
        "started_at": context.started_at,
        "completed_at": completed_at,
        "input_file": str(context.input_path) if context.input_path else "",
        "input_hash": context.input_hash,
        "validated_count": validated_count,
        "unresolved_count": unresolved_count,
        "status": status,
        "top_reasons": top_reasons,
    }
    with context.summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)

    context.index_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = context.index_path.exists()
    with context.index_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDEX_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(
            {
                "run_id": context.run_id,
                "started_at": context.started_at,
                "completed_at": completed_at,
                "input_file": str(context.input_path) if context.input_path else "",
                "input_hash": context.input_hash,
                "validated_count": validated_count,
                "unresolved_count": unresolved_count,
                "status": status,
                "top_reason": top_reason,
            }
        )


def update_progress(
    context: RunContext,
    *,
    processed: int,
    total: int,
    validated: int,
    unresolved: int,
    elapsed_sec: float,
    rate_per_min: float,
    eta_sec: float | None,
    last_result: str | None = None,
    last_reason: str | None = None,
) -> None:
    payload = {
        "run_id": context.run_id,
        "processed": processed,
        "total": total,
        "validated": validated,
        "unresolved": unresolved,
        "elapsed_sec": round(elapsed_sec, 2),
        "rate_per_min": round(rate_per_min, 2),
        "eta_sec": None if eta_sec is None else round(eta_sec, 2),
        "last_result": last_result or "",
        "last_reason": last_reason or "",
        "updated_at": datetime.utcnow().isoformat(),
    }
    with context.progress_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
