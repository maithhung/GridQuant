import copy
import json
import runpy
import sys
from pathlib import Path

import pytest
import yaml

from gridquant.demo import check_config, load_selections, run_demo

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def runner() -> dict:
    return runpy.run_path(str(ROOT / "final_evaluation.py"))


@pytest.fixture
def config() -> dict:
    return yaml.safe_load((ROOT / "configs/r1.yaml").read_text(encoding="utf-8"))


def test_frozen_configuration_and_saved_choices(runner: dict, config: dict) -> None:
    check_config(config)
    assert load_selections(config, input_dir=ROOT) == (100.0, "previous_day")


@pytest.mark.parametrize("change", ["dates", "feature", "unknown", "refit"])
def test_changed_configuration_is_rejected(
    runner: dict, config: dict, change: str
) -> None:
    altered = copy.deepcopy(config)
    if change == "dates":
        altered["splits"]["evaluation"][0] = "2023-03-11"
    elif change == "feature":
        altered["features"]["price_lag_days"] = [1, 2]
    elif change == "refit":
        altered["ridge"]["refit_during_evaluation"] = True
    else:
        altered["unexpected"] = True
    with pytest.raises(ValueError):
        check_config(altered)


def test_tampered_selection_is_rejected(
    runner: dict, config: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    for filename in ("ridge_validation.json", "seasonal_validation.json"):
        (reports / filename).write_bytes((ROOT / "reports" / filename).read_bytes())
    ridge_path = reports / "ridge_validation.json"
    result = json.loads(ridge_path.read_text())
    result["selected_alpha"] = 1.0
    ridge_path.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="Saved alpha disagrees"):
        load_selections(config, input_dir=tmp_path)


def test_existing_output_is_never_overwritten(
    runner: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "keep.txt"
    marker.write_text("existing result")
    monkeypatch.setattr(sys, "argv", ["final_evaluation.py", "--output", str(tmp_path)])
    with pytest.raises(FileExistsError, match="refusing overwrite"):
        runner["main"]()
    assert marker.read_text() == "existing result"


def test_missing_offline_input_creates_no_output(tmp_path: Path) -> None:
    output = tmp_path / "new-output"
    with pytest.raises(FileNotFoundError, match="Offline input is missing"):
        run_demo(input_dir=tmp_path / "missing", output_dir=output)
    assert not output.exists()


def test_online_mode_is_not_implied(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="only offline=True"):
        run_demo(input_dir=tmp_path, output_dir=tmp_path / "output", offline=False)


def test_relocated_inputs_reproduce_frozen_results_without_http(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import hashlib
    import socket
    import urllib.request

    from gridquant import demo

    def forbid_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("Network access is forbidden during replay")

    bundle = tmp_path / "bundle"
    names = [
        "configs/r1.yaml",
        "reports/ridge_validation.json",
        "reports/seasonal_validation.json",
        "data/raw/energy_charts/DE-LU/2023-01-01_2023-04-01.json",
        "data/processed/energy_charts/DE-LU/2023-01-01_2023-04-01.parquet",
    ]
    original_hashes = {}
    for name in names:
        target = bundle / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
        original_hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(urllib.request, "urlopen", forbid_network)
    monkeypatch.setattr(socket.socket, "connect", forbid_network)

    # Reproduction must not require Git to be installed.
    def missing_git(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("git unavailable")

    monkeypatch.setattr(demo.subprocess, "run", missing_git)
    result = run_demo(input_dir=bundle, output_dir=tmp_path / "run", offline=True)
    assert capsys.readouterr().out == ""
    baseline = json.loads((ROOT / "reports/final_evaluation/metrics.json").read_text())
    assert result.summary == baseline
    for name in ("predictions.json", "model.json", "quality.json", "report.md"):
        assert (result.output_dir / name).read_bytes() == (
            ROOT / "reports/final_evaluation" / name
        ).read_bytes()
    manifest = json.loads((result.output_dir / "manifest.json").read_text())
    assert manifest["git_revision"] is None
    assert manifest["git_dirty"] is None
    assert manifest["offline"] is True
    for name, digest in manifest["source_archive_sha256"].items():
        assert (
            hashlib.sha256(
                (result.output_dir / "source" / name).read_bytes()
            ).hexdigest()
            == digest
        )
    for name, digest in original_hashes.items():
        assert hashlib.sha256((bundle / name).read_bytes()).hexdigest() == digest


def test_wrapper_forwards_explicit_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gridquant import demo

    output = tmp_path / "result"
    output.mkdir()
    (output / "report.md").write_text("Example report")
    calls = []

    def fake_run(**kwargs: object) -> demo.DemoResult:
        calls.append(kwargs)
        return demo.DemoResult(output_dir=output, summary={})

    monkeypatch.setattr(demo, "run_demo", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        ["final_evaluation.py", "--input-dir", str(tmp_path), "--output", str(output)],
    )
    runpy.run_path(str(ROOT / "final_evaluation.py"), run_name="__main__")
    assert calls == [{"input_dir": tmp_path, "output_dir": output, "offline": True}]
