"""CLI for URL Discovery Engine."""

from __future__ import annotations

import asyncio
import csv
import time
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
from .resolvers.direct_resolver import DirectResolver
from .resolvers.breadcrumb_resolver import BreadcrumbResolver
from .resolvers.reverse_resolver import ReverseResolver

app = typer.Typer(add_completion=False)


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
