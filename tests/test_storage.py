import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from gridquant.data.storage import build_manifest, save_response


def test_manifest_records_download_and_copies_parameters() -> None:
    raw = b'{"price": -10}\n'
    parameters = {"bzn": "DE-LU"}
    manifest = build_manifest(
        raw,
        source="Example",
        endpoint="https://example.com/prices",
        parameters=parameters,
        retrieved_at=datetime(2026, 9, 28, 14, tzinfo=timezone(timedelta(hours=7))),
        license_info="Example license",
    )
    parameters["bzn"] = "FR"
    assert manifest == {
        "source": "Example",
        "endpoint": "https://example.com/prices",
        "parameters": {"bzn": "DE-LU"},
        "retrieved_at_utc": "2026-09-28T07:00:00+00:00",
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "license": "Example license",
    }


def test_naive_retrieval_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="UTC offset"):
        build_manifest(
            b"{}",
            source="Example",
            endpoint="example",
            parameters={},
            retrieved_at=datetime(2026, 9, 28),  # noqa: DTZ001 - intentionally invalid input
        )


def test_save_preserves_original_bytes_and_metadata(tmp_path: Path) -> None:
    raw = b'{ "price": -10 }\n'
    manifest = build_manifest(
        raw,
        source="Example",
        endpoint="example",
        parameters={},
        retrieved_at=datetime(2026, 9, 28, tzinfo=UTC),
    )
    sample = tmp_path / "nested" / "sample.json"
    save_response(sample, raw, manifest)
    assert sample.read_bytes() == raw
    assert (
        json.loads(sample.with_suffix(".manifest.json").read_text(encoding="utf-8"))
        == manifest
    )


@pytest.mark.parametrize("existing_suffix", [".json", ".manifest.json"])
def test_save_does_not_overwrite_existing_files(
    tmp_path: Path, existing_suffix: str
) -> None:
    sample = tmp_path / "sample.json"
    existing = sample.with_suffix(existing_suffix)
    existing.write_bytes(b"keep me")
    with pytest.raises(FileExistsError):
        save_response(sample, b"{}", {"raw_sha256": hashlib.sha256(b"{}").hexdigest()})
    assert existing.read_bytes() == b"keep me"
    assert len(list(tmp_path.iterdir())) == 1


def test_wrong_hash_leaves_no_files(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="hash"):
        save_response(tmp_path / "sample.json", b"{}", {"raw_sha256": "wrong"})
    assert not list(tmp_path.iterdir())


def test_unserializable_manifest_leaves_no_files(tmp_path: Path) -> None:
    manifest: dict[str, object] = {
        "raw_sha256": hashlib.sha256(b"{}").hexdigest(),
        "invalid": object(),
    }
    with pytest.raises(TypeError):
        save_response(tmp_path / "sample.json", b"{}", manifest)
    assert not list(tmp_path.iterdir())
