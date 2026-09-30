from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class PriceInterval:
    delivery_start_utc: datetime
    delivery_end_utc: datetime
    price_eur_per_mwh: float
    bidding_zone: str


@dataclass(frozen=True)
class DatasetMetadata:
    source: str
    source_document_id: str
    raw_sha256: str
    retrieved_at_utc: datetime

    source_publication_date: datetime | None = None
    source_revision: str | None = None
    availability_evidence: Literal["available", "unavailable", "unknown"] = "unknown"
    availability_note: str | None = None


@dataclass(frozen=True)
class PriceDataset:
    series_id: str
    metadata: DatasetMetadata
    intervals: tuple[PriceInterval, ...]
    schema_version: int = 1
