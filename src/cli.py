"""CLI for URL Discovery Engine."""

from __future__ import annotations

import asyncio
import csv
import json
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import typer

from .models import CompanyRecord, UnresolvedRecord, UNRESOLVED_CSV_FIELDS
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
from .extractors.company_name import slug_to_company_name
from .resolvers.direct_resolver import DirectResolver
from .resolvers.breadcrumb_resolver import BreadcrumbResolver
from .resolvers.reverse_resolver import ReverseResolver
from .resolvers.careers_resolver import CareersResolver, load_inputs, ats_family, expected_outcome
from .resolvers.phase1_careers_resolver import Phase1CareersResolver, Phase1HTTPClient
from .resolvers.phase2_ats_resolver import Phase2ATSResolver, load_phase2_inputs
from .utils.logging import setup_debug_logging

app = typer.Typer(add_completion=False)


def _print_careers_summary(results) -> None:
    status_counts: dict[str, int] = {}
    family_counts: dict[str, dict[str, int]] = {}

    for record, info in results:
        status_counts[info.status] = status_counts.get(info.status, 0) + 1
        family = ats_family(record.company_ats_name)
        family_stats = family_counts.setdefault(family, {"RESOLVED": 0, "PARTIAL": 0, "NOT_FOUND": 0, "CONFLICT": 0, "ERROR": 0})
        family_stats[info.status] = family_stats.get(info.status, 0) + 1

    total = sum(status_counts.values())
    print("\nCareers Resolver Summary")
    print(f"Total rows: {total}")
    for status in ["RESOLVED", "PARTIAL", "NOT_FOUND", "CONFLICT", "ERROR"]:
        if status in status_counts:
            print(f"{status}: {status_counts[status]}")

    print("\nBy ATS family:")
    for family, counts in family_counts.items():
        expected = expected_outcome(family)
        expected_primary = expected.get("expected_primary", "")
        expected_notes = expected.get("notes", "")
        total_family = sum(counts.values())
        alignment = None
        if expected_primary:
            alignment = (counts.get(expected_primary, 0) / total_family) if total_family else 0
        print(f"{family}:")
        print(f"  RESOLVED: {counts.get('RESOLVED', 0)}")
        print(f"  PARTIAL: {counts.get('PARTIAL', 0)}")
        print(f"  NOT_FOUND: {counts.get('NOT_FOUND', 0)}")
        if expected_primary:
            print(f"  Alignment: {alignment:.0%}")
            print(f"  Expected: {expected_primary} ({expected_notes})")

QA_EXPORT_FIELDS = [
    "input_url",
    "reason",
    "attempted_at",
    "qa_action",
    "company_ats_url",
    "company_name_clean",
    "company_domain",
    "corporate_url",
    "notes",
]

QA_APPLY_FIELDS = [
    "input_url",
    "qa_action",
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
    # Check if using new enhanced format or legacy format
    if rows and any(field in rows[0] for field in ["error_category", "validation_signals"]):
        fieldnames = UNRESOLVED_CSV_FIELDS
    elif rows and "company_ats_url" in rows[0]:
        fieldnames = QA_EXPORT_FIELDS
    else:
        fieldnames = ["input_url", "ats_name", "reason", "attempted_at"]
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
                        "qa_action": row.get("qa_action", ""),
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
                        "error_category": row.get("error_category", ""),
                        "validation_signals": row.get("validation_signals", ""),
                        "http_status": row.get("http_status", ""),
                        "final_url": row.get("final_url", ""),
                        "attempted_at": row.get("attempted_at", ""),
                    }
                )


def _load_urls(csv_path: str, limit: Optional[int] = None) -> list[str]:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(csv_path)
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames and "url" in reader.fieldnames:
            urls = [row.get("url", "").strip() for row in reader if row.get("url")]
            return urls[:limit] if limit else urls
        handle.seek(0)
        plain_reader = csv.reader(handle)
        urls = []
        for row in plain_reader:
            if not row:
                continue
            urls.append(row[0].strip())
            if limit and len(urls) >= limit:
                break
        return urls


def _pick_method(url: str) -> str:
    if detect(url):
        return "breadcrumb" if is_job_url(url) else "direct"
    return "reverse"


def _guess_company_slug(row: dict) -> Optional[str]:
    for key in ("final_url", "input_url"):
        value = (row.get(key) or "").strip()
        if not value:
            continue
        detection = detect(value)
        if detection:
            _, slug = detection
            return slug
    return None


def _guess_company_urls(slug: Optional[str]) -> list[str]:
    if not slug:
        return []
    cleaned = slug.strip().lower()
    if not cleaned:
        return []
    if "." in cleaned and "/" not in cleaned:
        return [f"https://{cleaned}"]
    base = re.sub(r"[^a-z0-9-]", "", cleaned)
    if not base:
        return []
    candidates = [
        f"https://{base}.com",
        f"https://{base}.io",
        f"https://{base}.ai",
        f"https://{base}.co",
        f"https://{base}.net",
        f"https://{base}.org",
    ]
    return candidates


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
                    "qa_action": "",
                    "company_ats_url": "",
                    "company_name_clean": "",
                    "company_domain": "",
                    "corporate_url": "",
                    "notes": "",
                }
            )


@app.command("company-suggestions")
def company_suggestions(
    unresolved: str = "output/unresolved.csv",
    output: str = "output/company_suggestions.csv",
):
    """Generate company name and URL suggestions for unresolved rows."""
    rows = _load_csv_rows(unresolved)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "input_url",
        "ats_name",
        "reason",
        "final_url",
        "company_name_guess",
        "company_url_guesses",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            slug = _guess_company_slug(row)
            name_guess = slug_to_company_name(slug) if slug else ""
            url_guesses = ";".join(_guess_company_urls(slug))
            writer.writerow(
                {
                    "input_url": row.get("input_url", ""),
                    "ats_name": row.get("ats_name", ""),
                    "reason": row.get("reason", ""),
                    "final_url": row.get("final_url", ""),
                    "company_name_guess": name_guess,
                    "company_url_guesses": url_guesses,
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
            qa_action = (row.get("qa_action") or "").strip().lower()
            notes = (row.get("notes") or "").strip().lower()
            if qa_action in {"drop", "delete", "remove", "invalid", "nonexistent"} or (
                notes and any(token in notes for token in ("drop", "delete", "remove", "invalid", "nonexistent"))
            ):
                key = input_url or ats_url
                if key:
                    dropped_inputs[key] = notes
                continue
            if qa_action in {"skip", "hold", "later"}:
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
    verbose: bool,
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
    logger = setup_debug_logging(verbose=verbose) if verbose else None
    
    client = HTTPClient()
    direct = DirectResolver(client=client, mode=mode)
    breadcrumb = BreadcrumbResolver(client=client, mode=mode) 
    reverse = ReverseResolver(client=client, mode=mode)
    
    # Set logger if verbose mode - pass logger to resolve calls
    pass

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
        try:
            result = await task
        except Exception as e:
            # Handle exceptions from resolve_one function  
            error_record = UnresolvedRecord(
                input_url="<unknown>",
                ats_name="unknown",
                reason=f"Exception in resolve_one: {str(e)}",
                error_category="exception",
                http_status=None,
                final_url=None,
                validation_signals=None,
                attempted_at=datetime.now().isoformat()
            )
            append_unresolved_record(unresolved_path, error_record)
            unresolved_count += 1
            last_result = "exception"
            last_reason = str(e)
            if verbose:
                print(f"[VERBOSE] 💥 Exception: {str(e)}")
                print()
            processed += 1
            continue
            
        if isinstance(result, CompanyRecord):
            append_company_record(output_path, result)
            resolved += 1
            last_result = "validated"
            last_reason = ""
            if verbose:
                print(f"[VERBOSE] ✅ Resolved: {result.company_ats_url}")
                print(f"[VERBOSE]    Company: {result.company_name_clean}")
                print(f"[VERBOSE]    Domain: {result.company_domain}")
                print(f"[VERBOSE]    Corporate: {result.corporate_url}")
                print(f"[VERBOSE]    Method: {result.discovery_method}")
                print(f"[VERBOSE]    Confidence: {result.confidence}")
                print()
        else:
            append_unresolved_record(unresolved_path, result)
            unresolved_count += 1
            last_result = "unresolved"
            last_reason = result.reason
            if verbose:
                print(f"[VERBOSE] ❌ Failed: {result.input_url}")
                print(f"[VERBOSE]    ATS: {result.ats_name}")
                print(f"[VERBOSE]    Reason: {result.reason}")
                print(f"[VERBOSE]    Category: {result.error_category}")
                print(f"[VERBOSE]    HTTP Status: {result.http_status}")
                print(f"[VERBOSE]    Final URL: {result.final_url}")
                if result.validation_signals:
                    print(f"[VERBOSE]    Signals: {', '.join(result.validation_signals)}")
                print()
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
    output: str = typer.Option("output/output.csv", "--output"),
    unresolved: str = typer.Option("output/unresolved.csv", "--unresolved"),
    validated_output: str = typer.Option("output/validated.csv", "--validated-output"),
    unresolved_output: str = typer.Option("output/unresolved.csv", "--unresolved-output"),
    dedupe: bool = typer.Option(True, "--dedupe/--no-dedupe"),
    overwrite: bool = typer.Option(True, "--overwrite/--no-overwrite"),
    track: bool = typer.Option(True, "--track/--no-track"),
    run_root: str = "runs",
    progress: bool = typer.Option(True, "--progress/--no-progress"),
    progress_every: int = 1,
    progress_interval: float = 1.0,
    verbose: bool = typer.Option(False, "--verbose/-v"),
):
    """Resolve a single URL."""
    async def _run():
        run_context = None
        if track:
            run_context = create_run_context(
                run_root,
                validated_output,
                unresolved_output,
                input_file=None,
            )
        await _process_urls(
            [url],
            validated_output,
            unresolved_output,
            mode,
            method,
            concurrency=1,
            dedupe=dedupe,
            overwrite=overwrite,
            run_context=run_context,
            progress=progress,
            progress_every=progress_every,
            progress_interval=progress_interval,
            verbose=verbose,
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
    verbose: bool = typer.Option(False, "--verbose/-v"),
    limit: Optional[int] = typer.Option(None, "--limit"),
):
    """Process a batch of URLs from CSV."""
    urls = _load_urls(input_file, limit=limit)
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
            verbose=verbose,
        )
    asyncio.run(_run())


@app.command("careers-resolver")
def careers_resolver(
    input_file: str,
    output: str = "output/careers_resolved.csv",
    debug: str = "output/careers_debug.jsonl",
    concurrency: int = 5,
    max_fetches_per_row: int = typer.Option(4, "--max-fetches-per-row"),
    allow_homepage_fallback: bool = typer.Option(False, "--allow-homepage-fallback/--no-allow-homepage-fallback"),
    allow_master_override: bool = typer.Option(False, "--allow-master-override/--no-allow-master-override"),
    enable_sitemap_scan: bool = typer.Option(False, "--enable-sitemap-scan/--no-enable-sitemap-scan"),
    export_resolved: bool = typer.Option(False, "--export-resolved/--no-export-resolved"),
    export_partial: bool = typer.Option(False, "--export-partial/--no-export-partial"),
    export_not_found: bool = typer.Option(False, "--export-not-found/--no-export-not-found"),
    export_all: bool = typer.Option(True, "--export-all/--no-export-all"),
    include_confidence_tier: bool = typer.Option(False, "--include-confidence-tier/--no-include-confidence-tier"),
    limit: Optional[int] = typer.Option(None, "--limit"),
):
    """Resolve corporate careers URLs from ATS URLs."""
    inputs = load_inputs(input_file)
    if limit:
        inputs = inputs[:limit]
    resolver = CareersResolver(max_fetches=max_fetches_per_row)

    async def _run():
        results = await resolver.resolve_batch(
            inputs,
            concurrency=concurrency,
            fallback_homepage=allow_homepage_fallback,
            allow_master_override=allow_master_override,
            enable_sitemap_scan=enable_sitemap_scan,
        )

        def confidence_tier(status: str) -> str:
            if status == "RESOLVED":
                return "HIGH"
            if status == "PARTIAL":
                return "MEDIUM"
            return "NONE"

        export_set = set()
        if export_resolved:
            export_set.add("RESOLVED")
        if export_partial:
            export_set.add("PARTIAL")
        if export_not_found:
            export_set.add("NOT_FOUND")
        export_all_local = export_all
        if export_set:
            export_all_local = False
        if export_all_local or not export_set:
            export_set = {"RESOLVED", "PARTIAL", "NOT_FOUND", "CONFLICT", "ERROR"}

        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        header = [
            "company_ats_name",
            "company_ats_url",
            "company_name_clean",
            "company_domain",
            "corporate_url",
        ]
        if include_confidence_tier:
            header.append("confidence_tier")

        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            for record, info in results:
                if info.status not in export_set:
                    continue
                row = [
                    record.company_ats_name,
                    record.company_ats_url,
                    record.company_name_clean,
                    record.company_domain,
                    record.corporate_url,
                ]
                if include_confidence_tier:
                    row.append(confidence_tier(info.status))
                writer.writerow(row)

        debug_path = Path(debug)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        with debug_path.open("w", encoding="utf-8") as handle:
            for record, info in results:
                family = ats_family(record.company_ats_name)
                expectation = expected_outcome(family)
                handle.write(
                    json.dumps(
                        {
                            "company_ats_name": record.company_ats_name,
                            "company_ats_url": record.company_ats_url,
                            "ats_family": family,
                            "expected_primary": expectation.get("expected_primary", ""),
                            "expected_notes": expectation.get("notes", ""),
                            "status": info.status,
                            "confidence": info.confidence,
                            "confidence_tier": confidence_tier(info.status),
                            "evidence": info.evidence,
                            "fetches": info.fetches,
                            "notes": info.notes,
                        }
                    )
                    + "\n"
                )

        _print_careers_summary(results)

    asyncio.run(_run())


@app.command("phase1-careers")
def phase1_careers(
    input_file: str,
    output_dir: str = "/data/phase1/careers_discovery",
    jsonl_name: str = "phase1_careers_urls.jsonl",
    csv_name: Optional[str] = "phase1_careers_urls.csv",
    concurrency: int = 50,
    per_domain_concurrency: int = 5,
    timeout: float = 12.0,
    retries: int = 1,
    max_pages: int = 50,
):
    """Phase-1 careers discovery from company sites only."""
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(input_file)

    rows = []
    with input_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(row)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_path / jsonl_name
    csv_path = output_path / csv_name if csv_name else None

    client = Phase1HTTPClient(
        global_limit=concurrency,
        per_domain_limit=per_domain_concurrency,
        timeout=timeout,
        retries=retries,
    )
    resolver = Phase1CareersResolver(client=client, max_depth=2, max_pages=max_pages)

    async def _run():
        semaphore = asyncio.Semaphore(concurrency)
        results = []

        async def run_row(row: dict):
            async with semaphore:
                return await resolver.resolve_one(
                    company_name=row.get("company_name", "").strip(),
                    primary_domain=row.get("primary_domain", "").strip(),
                    website_url=row.get("website_url", "").strip(),
                    linkedin_url=row.get("linkedin_url", "").strip(),
                )

        tasks = [asyncio.create_task(run_row(row)) for row in rows]
        for task in asyncio.as_completed(tasks):
            results.append(await task)

        with jsonl_path.open("w", encoding="utf-8") as handle:
            for result in results:
                handle.write(
                    json.dumps(
                        {
                            "company_name": result.company_name,
                            "primary_domain": result.primary_domain,
                            "careers_url": result.careers_url,
                            "source": result.source,
                            "http_status": result.http_status,
                            "confidence": result.confidence,
                            "notes": result.notes,
                        }
                    )
                    + "\n"
                )

        if csv_path:
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "company_name",
                        "primary_domain",
                        "careers_url",
                        "source",
                        "http_status",
                        "confidence",
                        "notes",
                    ]
                )
                for result in results:
                    writer.writerow(
                        [
                            result.company_name,
                            result.primary_domain,
                            result.careers_url or "",
                            result.source or "",
                            result.http_status or "",
                            result.confidence,
                            result.notes,
                        ]
                    )

        await client.close()

    asyncio.run(_run())


@app.command("phase2-ats")
def phase2_ats(
    input_file: str,
    output_jsonl: str = "output/phase2_ats.jsonl",
    output_csv: Optional[str] = "output/phase2_ats.csv",
    concurrency: int = 10,
):
    """Phase-2 ATS detection from Phase-1 careers URLs."""
    inputs = load_phase2_inputs(input_file)
    resolver = Phase2ATSResolver()

    async def _run():
        results = await resolver.resolve_batch(inputs, concurrency=concurrency)

        out_path = Path(output_jsonl)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as handle:
            for result in results:
                handle.write(
                    json.dumps(
                        {
                            "company_name": result.company_name,
                            "careers_url": result.careers_url,
                            "ats_provider": result.ats_provider,
                            "ats_base_url": result.ats_base_url,
                            "confidence": result.confidence,
                            "detection_signals": result.detection_signals,
                        }
                    )
                    + "\n"
                )

        if output_csv:
            csv_path = Path(output_csv)
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "company_name",
                        "careers_url",
                        "ats_provider",
                        "ats_base_url",
                        "confidence",
                        "detection_signals",
                    ]
                )
                for result in results:
                    writer.writerow(
                        [
                            result.company_name,
                            result.careers_url,
                            result.ats_provider or "",
                            result.ats_base_url or "",
                            result.confidence,
                            ";".join(result.detection_signals),
                        ]
                    )

    asyncio.run(_run())


if __name__ == "__main__":
    app()
