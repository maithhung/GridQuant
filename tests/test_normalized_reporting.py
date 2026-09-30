import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from gridquant.data.models import DatasetMetadata, PriceDataset, PriceInterval
from gridquant.data.normalized import load_dataset, save_dataset
from gridquant.data.reporting import save_quality_reports


@pytest.fixture
def dataset() -> PriceDataset:
    start = datetime(2023, 10, 28, 22, tzinfo=UTC)
    return PriceDataset(
        series_id="day_ahead_price",
        metadata=DatasetMetadata(
            source="Synthetic",
            source_document_id="fixtures/autumn.json",
            raw_sha256="a" * 64,
            retrieved_at_utc=datetime(2026, 9, 30, tzinfo=UTC),
            availability_note="Historical publication time is unknown.",
        ),
        intervals=tuple(
            PriceInterval(
                start + timedelta(hours=i),
                start + timedelta(hours=i + 1),
                -10.25 + i,
                "DE-LU",
            )
            for i in range(25)
        ),
    )


@pytest.mark.parametrize("empty", [False, True])
def test_round_trip_preserves_values_and_metadata(
    tmp_path: Path, dataset: PriceDataset, empty: bool
) -> None:
    if empty:
        dataset = replace(dataset, intervals=())
    path = tmp_path / "processed" / "sample.parquet"
    save_dataset(path, dataset)
    assert load_dataset(path) == dataset
    original = path.read_bytes()
    save_dataset(path, dataset)
    assert path.read_bytes() == original


def test_known_publication_and_revision_round_trip(
    tmp_path: Path, dataset: PriceDataset
) -> None:
    metadata = replace(
        dataset.metadata,
        source_publication_date=datetime(2023, 10, 28, 12, tzinfo=UTC),
        source_revision="revision-1",
        availability_evidence="available",
    )
    dataset = replace(dataset, metadata=metadata)
    path = tmp_path / "sample.parquet"
    save_dataset(path, dataset)
    assert load_dataset(path) == dataset


def test_changed_dataset_cannot_overwrite(
    tmp_path: Path, dataset: PriceDataset
) -> None:
    path = tmp_path / "sample.parquet"
    save_dataset(path, dataset)
    original = path.read_bytes()
    with pytest.raises(FileExistsError, match="different content"):
        save_dataset(path, replace(dataset, intervals=dataset.intervals[1:]))
    assert path.read_bytes() == original


def test_storage_preserves_duplicate_order(
    tmp_path: Path, dataset: PriceDataset
) -> None:
    broken = replace(dataset, intervals=dataset.intervals[1:] + (dataset.intervals[1],))
    path = tmp_path / "sample.parquet"
    save_dataset(path, broken)
    assert load_dataset(path) == broken


@pytest.mark.parametrize("price", [float("nan"), float("inf")])
def test_nonfinite_prices_fail_before_writing(
    tmp_path: Path, dataset: PriceDataset, price: float
) -> None:
    broken = replace(
        dataset, intervals=(replace(dataset.intervals[0], price_eur_per_mwh=price),)
    )
    path = tmp_path / "sample.parquet"
    with pytest.raises(ValueError, match="finite"):
        save_dataset(path, broken)
    assert not path.exists()


def test_naive_timestamp_fails_before_writing(
    tmp_path: Path, dataset: PriceDataset
) -> None:
    broken = replace(
        dataset,
        metadata=replace(dataset.metadata, retrieved_at_utc=datetime(2026, 9, 30)),  # noqa: DTZ001
    )
    path = tmp_path / "sample.parquet"
    with pytest.raises(ValueError, match="UTC offset"):
        save_dataset(path, broken)
    assert not path.exists()


def test_unrecognized_format_is_rejected(tmp_path: Path, dataset: PriceDataset) -> None:
    path = tmp_path / "sample.parquet"
    save_dataset(path, dataset)
    table = pq.ParquetFile(path).read()
    metadata = json.loads(table.schema.metadata[b"gridquant"])
    metadata["schema_version"] = 99
    altered = tmp_path / "altered.parquet"
    pq.write_table(
        table.replace_schema_metadata({b"gridquant": json.dumps(metadata).encode()}),
        altered,
    )
    with pytest.raises(ValueError, match="Unsupported"):
        load_dataset(altered)


def test_reports_share_counts_diagnostics_and_provenance(
    tmp_path: Path, dataset: PriceDataset
) -> None:
    broken = replace(dataset, intervals=dataset.intervals[1:] + (dataset.intervals[1],))
    paths = save_quality_reports(
        broken, date(2023, 10, 29), 60, tmp_path / "quality.json"
    )
    document = json.loads(paths[0].read_text(encoding="utf-8"))
    markdown = paths[1].read_text(encoding="utf-8")
    coverage = document["coverage"]
    assert coverage["observed_count"] == coverage["expected_count"] == 25
    assert coverage["coverage_percent"] == 96.0
    assert not coverage["has_complete_start_grid"]
    assert coverage["missing_starts"] == [
        dataset.intervals[0].delivery_start_utc.isoformat()
    ]
    assert coverage["duplicate_starts"] == [
        dataset.intervals[1].delivery_start_utc.isoformat()
    ]
    assert "| Start coverage | 96.00% |" in markdown
    assert "| Complete start grid | No |" in markdown
    assert coverage["missing_starts"][0] in markdown
    assert coverage["duplicate_starts"][0] in markdown
    assert document["dataset"]["metadata"]["raw_sha256"] == dataset.metadata.raw_sha256
    assert dataset.metadata.raw_sha256 in markdown
    assert document["scope"] in markdown
    original = [path.read_bytes() for path in paths]
    save_quality_reports(broken, date(2023, 10, 29), 60, paths[0])
    assert [path.read_bytes() for path in paths] == original


def test_report_conflict_does_not_write_companion(
    tmp_path: Path, dataset: PriceDataset
) -> None:
    path = tmp_path / "quality.json"
    path.with_suffix(".md").write_text("Existing report", encoding="utf-8")
    with pytest.raises(FileExistsError, match="different content"):
        save_quality_reports(dataset, date(2023, 10, 29), 60, path)
    assert not path.exists()
    assert path.with_suffix(".md").read_text(encoding="utf-8") == "Existing report"
