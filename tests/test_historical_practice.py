"""Exercise historical-script ordering, offline replay, and failure artifacts."""

import hashlib
import json
import runpy
import sys
from pathlib import Path

import pytest

from gridquant.collectors import energy_charts

PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT / "historical_practice.py"
SAMPLE = Path("data/raw/energy_charts/DE-LU/2023-03-26_2023-03-26.json")
REPORT = Path("reports/quality/DE-LU/2023-03-26_2023-03-26.period.json")
PROCESSED = Path("data/processed/energy_charts/DE-LU/2023-03-26_2023-03-26.parquet")


@pytest.fixture
def offline_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    def forbid_http(*args: object, **kwargs: object) -> None:
        raise AssertionError("HTTP forbidden during replay")

    monkeypatch.setattr(energy_charts, "urlopen", forbid_http)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SCRIPT), "--offline", "--start", "2023-03-26", "--end", "2023-03-26"],
    )
    return tmp_path


def copy_sample(workspace: Path) -> None:
    for relative in (SAMPLE, SAMPLE.with_suffix(".manifest.json")):
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((PROJECT / relative).read_bytes())


def test_offline_replay_is_stable(offline_workspace: Path) -> None:
    copy_sample(offline_workspace)
    original_raw = SAMPLE.read_bytes()
    original_manifest = SAMPLE.with_suffix(".manifest.json").read_bytes()
    runpy.run_path(str(SCRIPT), run_name="__main__")
    first_report = REPORT.read_bytes()
    first_processed = PROCESSED.read_bytes()
    result = json.loads(first_report)
    assert result["passed"] is True
    assert result["quality"]["expected_count"] == 23
    assert result["quality"]["observed_count"] == 23
    runpy.run_path(str(SCRIPT), run_name="__main__")
    assert REPORT.read_bytes() == first_report
    assert PROCESSED.read_bytes() == first_processed
    assert SAMPLE.read_bytes() == original_raw
    assert SAMPLE.with_suffix(".manifest.json").read_bytes() == original_manifest


def test_offline_missing_input_never_downloads(offline_workspace: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Offline input is missing"):
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert not REPORT.exists()
    assert not PROCESSED.exists()


def test_bad_hash_is_rejected(offline_workspace: Path) -> None:
    copy_sample(offline_workspace)
    SAMPLE.write_bytes(SAMPLE.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="recorded hash"):
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert not REPORT.exists()
    assert not PROCESSED.exists()


def test_invalid_coverage_saves_report_before_failing(offline_workspace: Path) -> None:
    copy_sample(offline_workspace)
    response = json.loads(SAMPLE.read_bytes())
    response["data"].pop()
    raw = json.dumps(response).encode()
    SAMPLE.write_bytes(raw)
    manifest_path = SAMPLE.with_suffix(".manifest.json")
    manifest = json.loads(manifest_path.read_bytes())
    manifest["raw_sha256"] = hashlib.sha256(raw).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Dataset validation failed"):
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert json.loads(REPORT.read_bytes())["passed"] is False
    assert not PROCESSED.exists()
