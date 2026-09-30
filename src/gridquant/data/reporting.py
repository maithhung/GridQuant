"""Deterministic JSON and Markdown reports for interval-start coverage."""

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from gridquant.data.models import PriceDataset
from gridquant.data.normalized import dataset_description, utc_text
from gridquant.data.quality import check_daily_coverage


def save_quality_reports(
    dataset: PriceDataset,
    delivery_date: date,
    interval_minutes: int,
    json_path: Path,
) -> tuple[Path, Path]:
    """Compute coverage once and write matching JSON/Markdown reports.

    Identical outputs are reused; changed outputs require a new path. The two
    writes are sequential, not an atomic pair. A rerun can supply a missing file.
    """
    if json_path.suffix != ".json":
        raise ValueError("The quality report path must end in .json.")
    report = check_daily_coverage(dataset, delivery_date, interval_minutes)
    coverage = asdict(report)
    coverage["delivery_date"] = delivery_date.isoformat()
    coverage["coverage_percent"] = report.coverage_percent
    coverage["has_complete_start_grid"] = report.has_complete_start_grid
    for field in ("missing_starts", "duplicate_starts", "unexpected_starts"):
        coverage[field] = [utc_text(start) for start in getattr(report, field)]
    scope = (
        "Interval-start coverage only. Interval ends, price conflicts, record "
        "order, and forecast-time availability are not validated by this report."
    )
    description = dataset_description(dataset)
    document = {
        "report_schema_version": 1,
        "calendar_timezone": "Europe/Berlin",
        "dataset": description,
        "coverage": coverage,
        "scope": scope,
    }
    json_text = json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    lines = [
        f"# Price coverage: {delivery_date.isoformat()}",
        "",
        f"Calendar: Europe/Berlin. Expected resolution: {interval_minutes} minutes.",
        "",
        "| Measure | Result |",
        "| --- | --- |",
        f"| Expected intervals | {report.expected_count} |",
        f"| Observed records | {report.observed_count} |",
        f"| Unique matching starts | {report.matched_count} |",
        f"| Start coverage | {report.coverage_percent:.2f}% |",
        f"| Missing starts | {len(report.missing_starts)} |",
        f"| Duplicated starts | {len(report.duplicate_starts)} |",
        f"| Unexpected starts | {len(report.unexpected_starts)} |",
        f"| Complete start grid | {'Yes' if report.has_complete_start_grid else 'No'} |",
        "",
        scope,
        "",
        "## Provenance",
        "",
        f"Source: {dataset.metadata.source}",
        "",
        f"Source document: {dataset.metadata.source_document_id}",
        "",
        f"Raw SHA-256: `{dataset.metadata.raw_sha256}`",
        "",
        f"Retrieved: {utc_text(dataset.metadata.retrieved_at_utc)}",
        "",
        (
            f"Series: {dataset.series_id}. Unit: EUR/MWh. "
            f"Dataset schema: {dataset.schema_version}. "
            f"Normalization version: {description['normalization_version']}."
        ),
        "",
        f"Availability evidence: {dataset.metadata.availability_evidence}.",
        "",
        dataset.metadata.availability_note or "No availability note supplied.",
        "",
    ]
    for label, starts in (
        ("Missing starts", report.missing_starts),
        ("Duplicated starts", report.duplicate_starts),
        ("Unexpected starts", report.unexpected_starts),
    ):
        lines.extend([f"## {label} (UTC)", ""])
        lines.extend([f"- {utc_text(start)}" for start in starts] or ["None."])
        lines.append("")
    markdown_path = json_path.with_suffix(".md")
    outputs = ((json_path, json_text), (markdown_path, "\n".join(lines)))
    # Check both paths before writing either output.
    for path, content in outputs:
        if path.exists() and path.read_bytes() != content.encode("utf-8"):
            raise FileExistsError(
                f"Report already exists with different content: {path}"
            )
    for path, content in outputs:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as output:
                output.write(content.encode("utf-8"))
    return json_path, markdown_path
