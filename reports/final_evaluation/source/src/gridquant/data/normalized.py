"""Store one source snapshot as typed Parquet with embedded provenance."""

import json
import math
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from gridquant.data.models import DatasetMetadata, PriceDataset, PriceInterval

NORMALIZATION_VERSION = 1
PRICE_SCHEMA = pa.schema(
    [
        pa.field("delivery_start_utc", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("delivery_end_utc", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("price_eur_per_mwh", pa.float64(), nullable=False),
        pa.field("bidding_zone", pa.string(), nullable=False),
    ]
)


def utc_text(value: datetime) -> str:
    """Serialize an aware timestamp without assuming a local timezone."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamps must include a UTC offset.")
    return value.astimezone(UTC).isoformat()


def dataset_description(dataset: PriceDataset) -> dict[str, object]:
    """JSON-compatible identity, units, transformation version, and provenance."""
    if type(dataset.schema_version) is not int or dataset.schema_version != 1:
        raise ValueError("Unsupported GridQuant dataset schema version.")
    metadata = asdict(dataset.metadata)
    metadata["retrieved_at_utc"] = utc_text(dataset.metadata.retrieved_at_utc)
    published = dataset.metadata.source_publication_date
    metadata["source_publication_date"] = utc_text(published) if published else None
    return {
        "schema_version": dataset.schema_version,
        "normalization_version": NORMALIZATION_VERSION,
        "series_id": dataset.series_id,
        "unit": "EUR/MWh",
        "metadata": metadata,
    }


def save_dataset(path: Path, dataset: PriceDataset) -> None:
    """Write Parquet; reuse equal content and refuse to replace different data.

    Writes are not atomic. Row order, duplicates, and gaps are preserved so that
    storage does not silently repair data before quality reporting.
    """
    description = dataset_description(dataset)
    rows = []
    for interval in dataset.intervals:
        utc_text(interval.delivery_start_utc)
        utc_text(interval.delivery_end_utc)
        price = interval.price_eur_per_mwh
        if isinstance(price, bool) or not isinstance(price, (int, float)):
            raise TypeError("Prices must be numeric, not booleans.")
        if not math.isfinite(price):
            raise ValueError("Prices must be finite.")
        rows.append(asdict(interval))
    schema = PRICE_SCHEMA.with_metadata(
        {
            b"gridquant": json.dumps(
                description, sort_keys=True, allow_nan=False
            ).encode()
        }
    )
    table = pa.Table.from_pylist(rows, schema=schema)
    if path.exists():
        existing = pq.ParquetFile(path).read()
        if not existing.equals(table, check_metadata=True):
            raise FileExistsError("Processed dataset exists with different content.")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        pq.write_table(table, output)


def load_dataset(path: Path) -> PriceDataset:
    """Load GridQuant Parquet, checking its format and required provenance."""
    table = pq.ParquetFile(path).read()
    if not table.schema.remove_metadata().equals(PRICE_SCHEMA):
        raise ValueError("Unexpected normalized price schema.")
    encoded = (table.schema.metadata or {}).get(b"gridquant")
    if encoded is None:
        raise ValueError("Missing GridQuant metadata.")
    document = json.loads(encoded)
    if (
        type(document.get("schema_version")) is not int
        or document["schema_version"] != 1
        or document.get("normalization_version") != NORMALIZATION_VERSION
        or document.get("unit") != "EUR/MWh"
    ):
        raise ValueError("Unsupported dataset version or unit.")
    metadata = document["metadata"]
    for field in ("source", "source_document_id", "raw_sha256"):
        if not isinstance(metadata[field], str):
            raise TypeError(f"Invalid metadata field: {field}.")
    for field in ("source_revision", "availability_note"):
        if metadata[field] is not None and not isinstance(metadata[field], str):
            raise TypeError(f"Invalid metadata field: {field}.")
    if metadata["availability_evidence"] not in ("available", "unavailable", "unknown"):
        raise ValueError("Unknown availability evidence.")
    if not isinstance(document["series_id"], str):
        raise TypeError("Invalid series_id.")
    for field in ("retrieved_at_utc", "source_publication_date"):
        if metadata[field] is not None:
            parsed = datetime.fromisoformat(metadata[field])
            metadata[field] = datetime.fromisoformat(utc_text(parsed))
    if metadata["retrieved_at_utc"] is None:
        raise ValueError("Missing retrieval timestamp.")
    rows = table.to_pylist()
    for row in rows:
        if any(value is None for value in row.values()):
            raise ValueError("Normalized records cannot contain nulls.")
        if not math.isfinite(row["price_eur_per_mwh"]):
            raise ValueError("Prices must be finite.")
    return PriceDataset(
        series_id=document["series_id"],
        metadata=DatasetMetadata(**metadata),
        intervals=tuple(PriceInterval(**row) for row in rows),
        schema_version=document["schema_version"],
    )
