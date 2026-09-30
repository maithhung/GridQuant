import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

from gridquant.collectors.energy_charts import (
    PRICE_ENDPOINT,
    fetch_price_response,
    parse_price_response,
)
from gridquant.data.models import DatasetMetadata, PriceDataset
from gridquant.data.normalized import load_dataset, save_dataset
from gridquant.data.period_quality import check_hourly_period
from gridquant.data.storage import build_manifest, save_response


def encode_report_value(value: object) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


parser = argparse.ArgumentParser()
parser.add_argument("--start", type=date.fromisoformat, default=date(2023, 1, 1))
parser.add_argument("--end", type=date.fromisoformat, default=date(2023, 4, 1))
parser.add_argument(
    "--offline",
    action="store_true",
    help="Require saved input; never download.",
)
args = parser.parse_args()
if args.end < args.start:
    parser.error("--end must not precede --start")

# Select the bidding zone and local delivery dates.
parameters = {
    "bzn": "DE-LU",
    "start": args.start.isoformat(),
    "end": args.end.isoformat(),
}

# Use a separate file for each zone and date range.
sample_path = (
    Path("data/raw/energy_charts")
    / parameters["bzn"]
    / f"{parameters['start']}_{parameters['end']}.json"
)
manifest_path = sample_path.with_suffix(".manifest.json")

if sample_path.exists():
    # Load the saved response and its metadata.
    if not manifest_path.exists():
        raise ValueError(
            "Saved response has no manifest. Move the old sample aside and run again."
        )

    raw_bytes = sample_path.read_bytes()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Confirm that this sample belongs to the current request.
    if manifest["endpoint"] != PRICE_ENDPOINT or manifest["parameters"] != parameters:
        raise ValueError("Saved request does not match current parameters.")

    # Detect changes to the saved response.
    actual_hash = hashlib.sha256(raw_bytes).hexdigest()

    if actual_hash != manifest["raw_sha256"]:
        raise ValueError("Saved response does not match its recorded hash.")

    intervals = parse_price_response(raw_bytes.decode("utf-8"))

    print("Loaded and verified saved response.")

else:
    if manifest_path.exists():
        raise ValueError(
            "Manifest exists without its response. "
            "Move the old manifest aside and run again."
        )

    if args.offline:
        raise FileNotFoundError(f"Offline input is missing: {sample_path}")

    # Download the original response bytes.
    raw_bytes = fetch_price_response(parameters["start"], parameters["end"])

    retrieved_at = datetime.now(UTC)
    raw_json = raw_bytes.decode("utf-8")

    # Validate before saving the response as a usable sample.
    intervals = parse_price_response(raw_json)
    response_data = json.loads(raw_json)

    manifest = build_manifest(
        raw_bytes,
        source="Energy-Charts",
        endpoint=PRICE_ENDPOINT,
        parameters=parameters,
        retrieved_at=retrieved_at,
        license_info=response_data.get("license"),
    )
    save_response(sample_path, raw_bytes, manifest)

    print("Downloaded response and saved manifest.")

# Recover the original retrieval time from the saved manifest.
retrieved_at = datetime.fromisoformat(manifest["retrieved_at_utc"])

if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
    raise ValueError("Retrieval time must include a UTC offset.")

# Describe the source snapshot shared by these intervals.
metadata = DatasetMetadata(
    source=manifest["source"],
    source_document_id=sample_path.as_posix(),
    raw_sha256=manifest["raw_sha256"],
    retrieved_at_utc=retrieved_at.astimezone(UTC),
    availability_evidence="unknown",
    availability_note=(
        "Saved historical response; publication time and "
        "historical revision availability have not been established."
    ),
)

# Combine the parsed records with their source metadata.
dataset = PriceDataset(
    series_id="day_ahead_price",
    metadata=metadata,
    intervals=tuple(intervals),
)

report = check_hourly_period(
    dataset,
    start_date=date.fromisoformat(parameters["start"]),
    end_date=date.fromisoformat(parameters["end"]),
)

print(f"Expected intervals: {report.expected_count}")
print(f"Observed intervals: {report.observed_count}")
print(f"Passed: {report.passed}")

# Save diagnostics before rejecting invalid data or normalizing.
report_document = {
    "report_schema_version": 1,
    "calendar_timezone": "Europe/Berlin",
    "expected_interval_minutes": 60,
    "source_document_id": dataset.metadata.source_document_id,
    "raw_sha256": dataset.metadata.raw_sha256,
    "availability_evidence": dataset.metadata.availability_evidence,
    "passed": report.passed,
    "quality": asdict(report),
}


report_bytes = (
    json.dumps(
        report_document,
        default=encode_report_value,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )
    + "\n"
).encode("utf-8")

report_path = Path("reports/quality/DE-LU") / f"{sample_path.stem}.period.json"

if report_path.exists():
    if report_path.read_bytes() != report_bytes:
        raise FileExistsError(f"Different report already exists: {report_path}")
else:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("xb") as output:
        output.write(report_bytes)

if not report.passed:
    raise ValueError(f"Dataset validation failed; see {report_path}")

# Save the normalized snapshot separately from the original response.
processed_path = (
    Path("data/processed/energy_charts")
    / parameters["bzn"]
    / f"{sample_path.stem}.parquet"
)
save_dataset(processed_path, dataset)
if load_dataset(processed_path) != dataset:
    raise ValueError("Normalized dataset did not survive the storage round trip.")
print(f"Normalized dataset: {processed_path}")
print(f"Period quality report: {report_path}")

print(f"Series: {dataset.series_id}")
print(f"Source: {dataset.metadata.source}")
print(f"Intervals: {len(dataset.intervals)}")
print(f"First interval: {dataset.intervals[0] if dataset.intervals else None}")

# Display a short summary.
print(f"Sample: {sample_path}")
print(f"Retrieved: {manifest['retrieved_at_utc']}")
print(f"Parsed {len(intervals)} intervals")

for interval in intervals[:5]:
    print(
        f"{interval.delivery_start_utc.isoformat()} -> "
        f"{interval.delivery_end_utc.isoformat()}: "
        f"{interval.price_eur_per_mwh} EUR/MWh"
    )
