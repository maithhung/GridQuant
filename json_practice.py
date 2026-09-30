import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from gridquant.collectors.energy_charts import (
    PRICE_ENDPOINT,
    fetch_price_response,
    parse_price_response,
)
from gridquant.data.storage import build_manifest, save_response

from gridquant.data.models import DatasetMetadata, PriceDataset

# Select the bidding zone and local delivery dates.
parameters = {
    "bzn": "DE-LU",
    "start": "2026-09-26",
    "end": "2026-09-26",
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
