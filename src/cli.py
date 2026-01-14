"""CLI for URL Discovery Engine."""

from __future__ import annotations

import asyncio
import csv
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable

import typer

from .models import CompanyRecord, UnresolvedRecord
from .output.csv_writer import append_company_record, dedupe_company_file
from .output.run_tracker import (
    create_run_context,
    finalize_run,
    update_progress,
    RunContext,
)
from .output.unresolved_writer import append_unresolved_record
from .patterns.ats_patterns import detect, is_job_url
from .validators.http_validator import HTTPClient
from .extractors.domain import extract_domain
from .resolvers.direct_resolver import DirectResolver
from .resolvers.breadcrumb_resolver import BreadcrumbResolver
from .resolvers.reverse_resolver import ReverseResolver

app = typer.Typer(add_completion=False)

QA_EXPORT_FIELDS = [
    "input_url",
    "reason",
    "attempted_at",
    "company_ats_url",
    "company_name_clean",
    "company_domain",
    "corporate_url",
    "notes",
]

QA_APPLY_FIELDS = [
    "input_url",
    "company_ats_url",
    "company_name_clean",
    "company_domain",
    "corporate_url",
    "notes",
]


def _load_csv_rows(path: str) -> list[dict]:
    csv_path = Path(path)
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def _write_unresolved_rows(path: str, rows: list[dict]) -> None:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["input_url", "ats_name", "reason", "attempted_at"]
    if rows and "company_ats_url" in rows[0]:
        fieldnames = QA_EXPORT_FIELDS
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            if fieldnames == QA_EXPORT_FIELDS:
                writer.writerow(
                    {
                        "input_url": row.get("input_url", ""),
                        "reason": row.get("reason", ""),
                        "attempted_at": row.get("attempted_at", ""),
                        "company_ats_url": row.get("company_ats_url", ""),
                        "company_name_clean": row.get("company_name_clean", ""),
                        "company_domain": row.get("company_domain", ""),
                        "corporate_url": row.get("corporate_url", ""),
                        "notes": row.get("notes", ""),
                    }
                )
            else:
                writer.writerow(
                    {
                        "input_url": row.get("input_url", ""),
                        "ats_name": row.get("ats_name", ""),
                        "reason": row.get("reason", ""),
                        "attempted_at": row.get("attempted_at", ""),
                    }
                )


def _load_urls(csv_path: str) -> list[str]:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(csv_path)
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames and "url" in reader.fieldnames:
            return [row.get("url", "").strip() for row in reader if row.get("url")]
        handle.seek(0)
        plain_reader = csv.reader(handle)
        urls = []
        for row in plain_reader:
            if not row:
                continue
            urls.append(row[0].strip())
        return urls


def _pick_method(url: str) -> str:
    if detect(url):
        return "breadcrumb" if is_job_url(url) else "direct"
    return "reverse"


@app.command("qa-export")
def qa_export(
    unresolved: str = "output/unresolved.csv",
    output: str = "output/qa_template.csv",
):
    """Export unresolved rows into a QA template for manual fixes."""
    rows = _load_csv_rows(unresolved)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=QA_EXPORT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "input_url": row.get("input_url", ""),
                    "reason": row.get("reason", ""),
                    "attempted_at": row.get("attempted_at", ""),
                    "company_ats_url": "",
                    "company_name_clean": "",
                    "company_domain": "",
                    "corporate_url": "",
                    "notes": "",
                }
            )
    print(f"QA template written to {output_path} ({len(rows)} rows)")


@app.command("qa-apply")
def qa_apply(
    qa_file: str,
    unresolved_in: str = "output/unresolved.csv",
    validated: str = "output/validated.csv",
    unresolved_out: str = "output/unresolved.csv",
    mode: str = "strict",
    dedupe: bool = typer.Option(True, "--dedupe/--no-dedupe"),
    track: bool = typer.Option(True, "--track/--no-track"),
    run_root: str = "runs",
    progress: bool = typer.Option(True, "--progress/--no-progress"),
):
    """Apply manual QA fixes to unresolved rows and pull them into validated."""
    async def _run():
        qa_rows = _load_csv_rows(qa_file)
        if not qa_rows:
            print("No QA rows found.")
            return

        run_context = None
        if track:
            run_context = create_run_context(
                run_root,
                validated,
                unresolved_out,
                input_file=qa_file,
                snapshot_input=True,
            )

        unresolved_rows = _load_csv_rows(unresolved_in)
        unresolved_by_input: dict[str, dict] = {}
        unresolved_order: list[str] = []
        for row in unresolved_rows:
            input_url = (row.get("input_url") or "").strip()
            if not input_url:
                continue
            if input_url not in unresolved_by_input:
                unresolved_order.append(input_url)
            unresolved_by_input[input_url] = row

        resolved_inputs: set[str] = set()
        failed_inputs: dict[str, str] = {}
        dropped_inputs: dict[str, str] = {}

        client = HTTPClient()
        direct = DirectResolver(client=client, mode=mode)

        total = len(qa_rows)
        for idx, row in enumerate(qa_rows, start=1):
            input_url = (row.get("input_url") or "").strip()
            ats_url = (row.get("company_ats_url") or "").strip()
            notes = (row.get("notes") or "").strip().lower()
            if notes and any(token in notes for token in ("drop", "delete", "remove", "invalid", "nonexistent")):
                key = input_url or ats_url
                if key:
                    dropped_inputs[key] = notes
                continue
            if not ats_url:
                if input_url:
                    failed_inputs[input_url] = "QA missing company_ats_url"
                continue

            result = await direct.resolve(ats_url)
            key = input_url or ats_url
            if isinstance(result, CompanyRecord):
                manual_name = (row.get("company_name_clean") or "").strip()
                manual_domain = (row.get("company_domain") or "").strip()
                manual_corp = (row.get("corporate_url") or "").strip()

                updates: dict[str, str] = {}
                if manual_name:
                    updates["company_name_clean"] = manual_name
                if manual_corp and not detect(manual_corp):
                    corp_validation = await client.validate(manual_corp)
                    if corp_validation.status_code > 0 and corp_validation.status_code < 400 and not corp_validation.is_sso_redirect:
                        updates["corporate_url"] = corp_validation.final_url
                        if not manual_domain:
                            manual_domain = extract_domain(corp_validation.final_url) or ""
                if manual_domain:
                    updates["company_domain"] = manual_domain

                if updates:
                    result = result.model_copy(update=updates)

                append_company_record(validated, result)
                resolved_inputs.add(key)
            else:
                failed_inputs[key] = f"QA failed: {result.reason}"

            if progress and (idx % 10 == 0 or idx == total):
                print(
                    f"[qa] {idx}/{total} processed, resolved={len(resolved_inputs)}, "
                    f"failed={len(failed_inputs)}, dropped={len(dropped_inputs)}"
                )

        await client.close()

        if dedupe:
            dedupe_company_file(validated)

        updated_unresolved: list[dict] = []
        for input_url in unresolved_order:
            row = unresolved_by_input.get(input_url)
            if not row:
                continue
            if input_url in resolved_inputs:
                continue
            if input_url in dropped_inputs:
                continue
            if input_url in failed_inputs:
                row["reason"] = failed_inputs[input_url]
                row["attempted_at"] = datetime.utcnow().isoformat()
            updated_unresolved.append(row)

        for input_url, reason in failed_inputs.items():
            if input_url in unresolved_by_input:
                continue
            updated_unresolved.append(
                {
                    "input_url": input_url,
                    "ats_name": "",
                    "reason": reason,
                    "attempted_at": datetime.utcnow().isoformat(),
                }
            )

        if run_context and dropped_inputs:
            dropped_path = run_context.run_dir / "dropped.csv"
            with dropped_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["input_url", "notes", "dropped_at"])
                writer.writeheader()
                for input_url, note in dropped_inputs.items():
                    writer.writerow(
                        {
                            "input_url": input_url,
                            "notes": note,
                            "dropped_at": datetime.utcnow().isoformat(),
                        }
                    )

        _write_unresolved_rows(unresolved_out, updated_unresolved)

        if run_context:
            finalize_run(run_context)

    asyncio.run(_run())


async def _process_urls(
    urls: Iterable[str],
    output_path: str,
    unresolved_path: str,
    mode: str,
    method: str,
    concurrency: int,
    dedupe: bool,
    overwrite: bool,
    run_context: RunContext | None,
    progress: bool,
    progress_every: int,
    progress_interval: float,
) -> None:
    if overwrite:
        for path in (output_path, unresolved_path):
            target = Path(path)
            if target.exists():
                target.unlink()
    url_list = list(urls)
    total = len(url_list)
    if progress:
        print(f"Starting {total} URLs -> {output_path}, {unresolved_path}")
    client = HTTPClient()
    direct = DirectResolver(client=client, mode=mode)
    breadcrumb = BreadcrumbResolver(client=client, mode=mode)
    reverse = ReverseResolver(client=client, mode=mode)

    semaphore = asyncio.Semaphore(concurrency)

    async def resolve_one(url: str):
        async with semaphore:
            chosen = method
            if method == "auto":
                chosen = _pick_method(url)
            if chosen == "direct":
                return await direct.resolve(url)
            if chosen == "breadcrumb":
                return await breadcrumb.resolve(url)
            return await reverse.resolve(url)

    tasks = [asyncio.create_task(resolve_one(url)) for url in url_list]

    processed = 0
    resolved = 0
    unresolved_count = 0
    last_print = time.monotonic()
    started = last_print
    last_result = ""
    last_reason = ""

    for task in asyncio.as_completed(tasks):
        result = await task
        if isinstance(result, CompanyRecord):
            append_company_record(output_path, result)
            resolved += 1
            last_result = "validated"
            last_reason = ""
        else:
            append_unresolved_record(unresolved_path, result)
            unresolved_count += 1
            last_result = "unresolved"
            last_reason = result.reason
        processed += 1

        if progress:
            now = time.monotonic()
            should_print = (
                processed == total
                or (progress_every > 0 and processed % progress_every == 0)
                or (now - last_print) >= progress_interval
            )
            if should_print:
                elapsed = now - started
                rate = processed / elapsed if elapsed > 0 else 0.0
                rate_per_min = rate * 60
                eta_sec = None
                if rate > 0 and total:
                    eta_sec = max(0.0, (total - processed) / rate)
                percent = (processed / total * 100.0) if total else 100.0
                eta_display = f"{int(eta_sec)}s" if eta_sec is not None else "n/a"
                print(
                    f"[progress] {processed}/{total} ({percent:.1f}%) "
                    f"validated={resolved} unresolved={unresolved_count} "
                    f"rate={rate_per_min:.1f}/min eta={eta_display}"
                )
                if run_context:
                    update_progress(
                        run_context,
                        processed=processed,
                        total=total,
                        validated=resolved,
                        unresolved=unresolved_count,
                        elapsed_sec=elapsed,
                        rate_per_min=rate_per_min,
                        eta_sec=eta_sec,
                        last_result=last_result,
                        last_reason=last_reason,
                    )
                last_print = now

    await client.close()
    if dedupe:
        dedupe_company_file(output_path)
    if run_context:
        finalize_run(run_context)


@app.command()
def resolve(
    url: str,
    mode: str = "strict",
    method: str = "auto",
    output: str = "output/output.csv",
    unresolved: str = "output/unresolved.csv",
    dedupe: bool = typer.Option(True, "--dedupe/--no-dedupe"),
    overwrite: bool = typer.Option(True, "--overwrite/--no-overwrite"),
    track: bool = typer.Option(True, "--track/--no-track"),
    run_root: str = "runs",
    progress: bool = typer.Option(True, "--progress/--no-progress"),
    progress_every: int = 1,
    progress_interval: float = 1.0,
):
    """Resolve a single URL."""
    async def _run():
        run_context = None
        if track:
            run_context = create_run_context(
                run_root,
                output,
                unresolved,
                input_file=None,
            )
        await _process_urls(
            [url],
            output,
            unresolved,
            mode,
            method,
            concurrency=1,
            dedupe=dedupe,
            overwrite=overwrite,
            run_context=run_context,
            progress=progress,
            progress_every=progress_every,
            progress_interval=progress_interval,
        )
    asyncio.run(_run())


@app.command()
def batch(
    input_file: str,
    output: str = "output/output.csv",
    unresolved: str = "output/unresolved.csv",
    mode: str = "strict",
    method: str = "auto",
    concurrency: int = 20,
    dedupe: bool = typer.Option(True, "--dedupe/--no-dedupe"),
    overwrite: bool = typer.Option(True, "--overwrite/--no-overwrite"),
    track: bool = typer.Option(True, "--track/--no-track"),
    run_root: str = "runs",
    snapshot_input: bool = True,
    progress: bool = typer.Option(True, "--progress/--no-progress"),
    progress_every: int = 25,
    progress_interval: float = 10.0,
):
    """Process a batch of URLs from CSV."""
    urls = _load_urls(input_file)
    async def _run():
        run_context = None
        if track:
            run_context = create_run_context(
                run_root,
                output,
                unresolved,
                input_file=input_file,
                snapshot_input=snapshot_input,
            )
        await _process_urls(
            urls,
            output,
            unresolved,
            mode,
            method,
            concurrency,
            dedupe,
            overwrite,
            run_context=run_context,
            progress=progress,
            progress_every=progress_every,
            progress_interval=progress_interval,
        )
    asyncio.run(_run())


if __name__ == "__main__":
    app()
