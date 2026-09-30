"""Reusable offline forecasting workflow for the future R1 demo command.

The input directory contains configs/, data/, and reports/ in the existing
project layout. Synthetic merit-order examples accompany the frozen forecasts.
"""

import hashlib
import json
import platform
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from importlib.metadata import version
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import yaml  # type: ignore[import-untyped]

from gridquant.data.normalized import load_dataset
from gridquant.data.period_quality import check_hourly_period
from gridquant.demo_bundle import BUNDLE_MANIFEST, verify_bundle, verify_raw_manifest
from gridquant.evaluation import mae_skill, weighted_metrics
from gridquant.merit_order import GeneratorOffer, clear_market
from gridquant.models.ridge import RidgePrediction, fit_ridge, forecast_ridge
from gridquant.models.seasonal import SeasonalPrediction, forecast_seasonal

PACKAGE_DIR = Path(__file__).resolve().parent
BERLIN = ZoneInfo("Europe/Berlin")
EXPERIMENT = "r1_hourly_2023_v1"
BLOCKS = [
    ["2023-02-19", "2023-02-25"],
    ["2023-02-26", "2023-03-04"],
    ["2023-03-05", "2023-03-11"],
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def write_json(path: Path, document: object) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(
            document,
            output,
            default=json_default,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        output.write("\n")


def load_selections(config: dict[str, Any], *, input_dir: Path) -> tuple[float, str]:
    """Verify saved choices against their validation-only scores and dates."""
    ridge = json.loads((input_dir / "reports/ridge_validation.json").read_text())
    seasonal = json.loads((input_dir / "reports/seasonal_validation.json").read_text())
    require(
        ridge["experiment_id"] == seasonal["experiment_id"] == EXPERIMENT,
        "Selection reports refer to a different experiment.",
    )
    require(
        [seasonal["validation_start"], seasonal["validation_end"]]
        == [BLOCKS[0][0], BLOCKS[-1][1]],
        "Seasonal validation dates differ.",
    )
    require(
        seasonal["prediction_counts"] == {"previous_day": 504, "previous_week": 504},
        "Seasonal validation coverage differs.",
    )
    alphas = config["ridge"]["alphas"]
    scores = {
        float(key): float(value) for key, value in ridge["pooled_mae_by_alpha"].items()
    }
    require(set(scores) == set(alphas), "Ridge candidate grid differs.")
    require(
        all(np.isfinite(score) and score >= 0 for score in scores.values()),
        "Invalid Ridge validation score.",
    )
    require(len(ridge["blocks"]) == 12, "Expected twelve Ridge validation fits.")
    for alpha in alphas:
        rows = [row for row in ridge["blocks"] if row["alpha"] == alpha]
        require(len(rows) == 3, "Expected three blocks per alpha.")
        rows.sort(key=lambda row: row["block"])
        for index, (row, block) in enumerate(zip(rows, BLOCKS, strict=True), start=1):
            require(
                row["block"] == index
                and [row["validation_start"], row["validation_end"]] == block
                and row["training_end"]
                == (date.fromisoformat(block[0]) - timedelta(days=1)).isoformat()
                and row["predictions"] == 168,
                "Invalid Ridge validation block.",
            )
        require(
            abs(sum(row["mae_eur_per_mwh"] for row in rows) / 3 - scores[alpha]) < 1e-9,
            "Ridge pooled score does not match block scores.",
        )
    selected = min(alphas, key=lambda alpha: (scores[alpha], -alpha))
    require(
        ridge["selected_alpha"] == selected,
        "Saved alpha disagrees with validation selection.",
    )
    seasonal_scores = seasonal["mae_eur_per_mwh"]
    require(
        set(seasonal_scores) == {"previous_day", "previous_week"}
        and all(
            np.isfinite(score) and score >= 0 for score in seasonal_scores.values()
        ),
        "Invalid seasonal scores.",
    )
    best = min(seasonal_scores.values())
    reference = (
        "previous_day"
        if seasonal_scores["previous_day"] <= 1.01 * best
        else "previous_week"
    )
    require(
        seasonal["selected_reference"] == reference,
        "Saved seasonal selection disagrees.",
    )
    return float(selected), reference


def check_config(config: dict[str, Any]) -> None:
    """This runner implements only the frozen R1 hourly experiment."""
    expected: dict[str, Any] = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT,
        "data.zone": "DE-LU",
        "data.series": "day_ahead_price",
        "data.unit": "EUR/MWh",
        "data.timezone": "Europe/Berlin",
        "data.interval_minutes": 60,
        "data.evidence_track": "latest_vintage",
        "forecast.origin_local_time": "11:00",
        "forecast.origin_days_before_delivery": 1,
        "forecast.assume_previous_day_curve_available": True,
        "splits.warmup": ["2023-01-01", "2023-01-07"],
        "splits.training": ["2023-01-08", "2023-02-18"],
        "splits.validation": BLOCKS,
        "splits.evaluation": ["2023-03-12", "2023-04-01"],
        "features.price_lag_days": [1, 7],
        "features.calendar": ["hour", "weekday", "repeated_hour_occurrence"],
        "features.numeric_scaling": "standard",
        "features.categorical_encoding": "fixed_one_hot",
        "features.hour_categories": list(range(24)),
        "features.weekday_categories": list(range(7)),
        "features.occurrence_categories": [0, 1],
        "features.missing_price_policy": "fail",
        "alignment.key": "local_hour_and_occurrence",
        "alignment.missing_occurrence": "same_hour_available_occurrence",
        "alignment.missing_hour": "source_day_mean",
        "alignment.incomplete_source_day": "fail",
        "ridge.alphas": [0.1, 1.0, 10.0, 100.0],
        "ridge.fit_intercept": True,
        "ridge.validation_refit": "before_each_block",
        "ridge.validation_training_window": "expanding",
        "ridge.final_refit": "once_before_evaluation",
        "ridge.refit_during_evaluation": False,
        "ridge.alpha_tie_break": "larger_alpha",
        "selection.metric": "pooled_validation_duration_weighted_mae",
        "selection.seasonal_tie_relative_tolerance": 0.01,
        "selection.seasonal_tie_preference": "previous_day",
        "selection.seasonal_zero_mae_tie": "exact_zero_only",
        "evaluation.metrics": ["mae", "rmse", "bias"],
        "evaluation.weighting": "interval_duration_hours",
        "evaluation.comparison_intervals": "common_successful_targets",
        "evaluation.unexplained_prediction_failures_block_release": True,
        "evaluation.bias_sign": "prediction_minus_actual",
        "evaluation.report_prediction_failures": True,
        "evaluation.report_dst_substitutions": True,
        "evaluation.high_price_quantile": 0.95,
        "evaluation.high_price_threshold_source": "initial_training_targets",
        "evaluation.high_price_quantile_method": "linear",
        "evaluation.breakdowns": [
            "delivery_day",
            "month",
            "local_hour",
            "negative_price",
            "high_price",
        ],
        "evaluation.metric_reproduction_tolerance": 0.000001,
    }
    for dotted, value in expected.items():
        observed: Any = config
        for key in dotted.split("."):
            observed = observed[key]
        require(observed == value, f"Unsupported frozen setting: {dotted}")
    allowed = set(expected) | {
        "data.raw_path",
        "data.raw_sha256",
        "data.processed_path",
        "data.processed_sha256",
        "data.quality_report_path",
    }
    observed_keys = {
        key if not isinstance(value, dict) else f"{key}.{child}"
        for key, value in config.items()
        for child in (value if isinstance(value, dict) else [None])
    }
    require(observed_keys == allowed, "Unknown or missing configuration keys.")


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return asdict(
        weighted_metrics(
            [row["actual_eur_per_mwh"] for row in rows],
            [row["prediction_eur_per_mwh"] for row in rows],
            [row["duration_hours"] for row in rows],
        )
    )


@dataclass(frozen=True)
class DemoResult:
    """Completed output location and metrics for a script or CLI to display."""

    output_dir: Path
    summary: dict[str, Any]


def run_merit_order_examples() -> dict[str, Any]:
    """Run the three agreed synthetic hand examples with explicit units."""
    offers = [GeneratorOffer("A", 50.0, 10.0), GeneratorOffer("B", 100.0, 40.0),
              GeneratorOffer("C", 80.0, 70.0)]
    cases = []
    for case_id, demand, duration in (
        ("served_one_hour", 120.0, 1.0),
        ("served_quarter_hour", 120.0, 0.25),
        ("shortage_half_hour", 300.0, 0.5),
    ):
        result = clear_market(offers, demand_mw=demand, duration_hours=duration)
        cases.append({
            "case_id": case_id, "demand_mw": demand, "duration_hours": duration,
            "status": "shortage" if result.unmet_demand_mw > 0 else "cleared",
            "result": asdict(result),
        })
    return {
        "schema_version": 1, "input_kind": "synthetic", "offers": [asdict(offer) for offer in offers],
        "units": {"power": "MW", "energy": "MWh", "duration": "hours", "price": "EUR/MWh", "operating_profit": "EUR"},
        "shortage_policy": "The highest marginal cost among positive-dispatch units sets the price; unmet demand earns no revenue. No scarcity premium is modeled.",
        "limitations": "Operating profit excludes fixed and startup costs. This synthetic fleet is not calibrated to the historical price dataset.",
        "cases": cases,
    }


def input_path(input_dir: Path, relative: str) -> Path:
    """Resolve bundle-relative files without falling back to outside inputs."""
    path = (input_dir / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(input_dir):
        raise ValueError(f"Input path must stay inside input_dir: {relative}")
    if not path.is_file():
        raise FileNotFoundError(f"Offline input is missing: {path}")
    return path


def run_demo(*, input_dir: Path, output_dir: Path, offline: bool = True) -> DemoResult:
    """Reproduce frozen forecasts using explicit local inputs and new outputs.

    No argument parsing, console output, downloads, or current-directory data
    lookup occurs here. Only offline=True is supported at this stage. Existing
    outputs are refused; prediction failures retain diagnostics and raise.
    """
    if offline is not True:
        raise ValueError("This workflow currently supports only offline=True.")
    input_dir = input_dir.resolve()
    output = output_dir.resolve()
    if output.exists():
        raise FileExistsError(f"Run already exists; refusing overwrite: {output}")
    started = time.perf_counter()
    bundle = verify_bundle(input_dir) if (input_dir / BUNDLE_MANIFEST).exists() else None
    config_path = input_path(input_dir, "configs/r1.yaml")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise TypeError("Configuration must be a mapping.")
    check_config(config)
    for selection in (
        "reports/ridge_validation.json",
        "reports/seasonal_validation.json",
    ):
        input_path(input_dir, selection)
    alpha, reference = load_selections(config, input_dir=input_dir)
    raw_path = input_path(input_dir, config["data"]["raw_path"])
    processed_path = input_path(input_dir, config["data"]["processed_path"])
    raw_manifest_path = verify_raw_manifest(input_dir, config)
    provenance_paths = [
        raw_path, processed_path, raw_manifest_path, config_path,
        input_dir / "reports/ridge_validation.json", input_dir / "reports/seasonal_validation.json",
    ]
    if bundle is not None:
        required = {path.relative_to(input_dir).as_posix() for path in provenance_paths}
        required.update({"ATTRIBUTION.md", "expected/forecast_metrics.json", config["data"]["quality_report_path"]})
        require(required.issubset(bundle["files"]), "Bundle inventory omits required inputs.")
        provenance_paths = [input_path(input_dir, name) for name in bundle["files"]]
        provenance_paths.append(input_dir / BUNDLE_MANIFEST)
    for path, key in ((raw_path, "raw_sha256"), (processed_path, "processed_sha256")):
        require(
            sha256(path).lower() == config["data"][key].lower(),
            f"Snapshot hash mismatch: {path}",
        )
    dataset = load_dataset(processed_path)
    require(
        dataset.metadata.raw_sha256.lower() == sha256(raw_path),
        "Parquet provenance hash mismatch.",
    )
    quality = check_hourly_period(dataset, date(2023, 1, 1), date(2023, 4, 1))
    require(
        quality.passed and quality.expected_count == 2183,
        "Dataset quality gate failed.",
    )
    dispatch = run_merit_order_examples()
    initial_prices = [
        row.price_eur_per_mwh
        for row in dataset.intervals
        if date(2023, 1, 8)
        <= row.delivery_start_utc.astimezone(BERLIN).date()
        <= date(2023, 2, 18)
    ]
    threshold = float(np.quantile(initial_prices, 0.95, method="linear"))
    # Exactly one final fit; no evaluation targets are used in fitting.
    model = fit_ridge(dataset, date(2023, 1, 8), date(2023, 3, 11), alpha=alpha)
    all_predictions: list[SeasonalPrediction | RidgePrediction] = []
    day = date(2023, 3, 12)
    while day <= date(2023, 4, 1):
        all_predictions.extend(forecast_seasonal(dataset, day, lag_days=1))
        all_predictions.extend(forecast_seasonal(dataset, day, lag_days=7))
        all_predictions.extend(forecast_ridge(model, dataset, day))
        day += timedelta(days=1)
    # Attach actuals only after all predictions are produced.
    targets = {
        row.delivery_start_utc: row
        for row in dataset.intervals
        if date(2023, 3, 12)
        <= row.delivery_start_utc.astimezone(BERLIN).date()
        <= date(2023, 4, 1)
    }
    require(len(targets) == 503, "Expected 503 evaluation targets.")
    by_model: dict[str, list[dict[str, Any]]] = {
        name: [] for name in ("previous_day", "previous_week", "ridge")
    }
    for prediction in all_predictions:
        row = asdict(prediction)
        actual = targets[prediction.delivery_start_utc]
        require(
            prediction.delivery_end_utc == actual.delivery_end_utc,
            "Prediction/target interval mismatch.",
        )
        local = prediction.delivery_start_utc.astimezone(BERLIN)
        row.update(
            actual_eur_per_mwh=actual.price_eur_per_mwh,
            error_eur_per_mwh=(
                None
                if prediction.prediction_eur_per_mwh is None
                else prediction.prediction_eur_per_mwh - actual.price_eur_per_mwh
            ),
            duration_hours=(
                prediction.delivery_end_utc - prediction.delivery_start_utc
            ).total_seconds()
            / 3600,
            local_delivery_date=local.date().isoformat(),
            local_hour=local.hour,
            month=local.strftime("%Y-%m"),
        )
        by_model[prediction.model_id].append(row)
    successful = {}
    coverage = {}
    for name, rows in by_model.items():
        starts = [row["delivery_start_utc"] for row in rows]
        require(
            len(starts) == len(set(starts)) and set(starts) == set(targets),
            "Prediction grid mismatch.",
        )
        good = [
            row
            for row in rows
            if row["failure_reason"] is None
            and row["prediction_eur_per_mwh"] is not None
        ]
        successful[name] = {row["delivery_start_utc"] for row in good}
        substitutions = sum(
            any(
                lag["substitution"] != "none"
                for lag in (
                    row["features"]["previous_day"],
                    row["features"]["previous_week"],
                )
            )
            if name == "ridge"
            else row["substitution"] != "none"
            for row in rows
        )
        coverage[name] = {
            "planned": 503,
            "successful": len(good),
            "failures": 503 - len(good),
            "duration_coverage_percent": 100
            * sum(row["duration_hours"] for row in good)
            / 503,
            "substituted_predictions": substitutions,
        }
    common = set.intersection(*successful.values())
    metrics = {}
    breakdowns = {}
    for name, rows in by_model.items():
        matched = [row for row in rows if row["delivery_start_utc"] in common]
        metrics[name] = summarize(matched)
        groups = {
            "negative_price": [row for row in matched if row["actual_eur_per_mwh"] < 0],
            "high_price": [
                row for row in matched if row["actual_eur_per_mwh"] > threshold
            ],
        }
        for field in ("local_delivery_date", "month", "local_hour"):
            for value in sorted({row[field] for row in rows}):
                groups[f"{field}:{value}"] = [
                    row for row in matched if row[field] == value
                ]
        breakdowns[name] = {
            group: summarize(values) for group, values in groups.items()
        }
    skill = mae_skill(metrics["ridge"]["mae"], metrics[reference]["mae"])
    passed = all(item["failures"] == 0 for item in coverage.values())
    summary = {
        "experiment_id": EXPERIMENT,
        "evaluation_start": "2023-03-12",
        "evaluation_end": "2023-04-01",
        "selected_alpha": alpha,
        "selected_reference": reference,
        "training_rows": model.training_rows,
        "common_intervals": len(common),
        "coverage": coverage,
        "metrics_eur_per_mwh": metrics,
        "ridge_skill_against_reference": skill,
        "high_price_threshold_eur_per_mwh": threshold,
        "breakdowns": breakdowns,
        "passed": passed,
    }
    output.mkdir(parents=True)
    write_json(output / "dispatch.json", dispatch)
    write_json(output / "metrics.json", summary)
    write_json(output / "predictions.json", by_model)
    write_json(output / "quality.json", asdict(quality))
    write_json(output / "resolved_config.json", config)
    scaler = model.pipeline.named_steps["preprocess"].named_transformers_["prices"]
    estimator = model.pipeline.named_steps["ridge"]
    write_json(
        output / "model.json",
        {
            "alpha": alpha,
            "training_start": model.training_start,
            "training_end": model.training_end,
            "training_rows": model.training_rows,
            "solver": "svd",
            "price_means": scaler.mean_.tolist(),
            "price_scales": scaler.scale_.tolist(),
            "coefficients": estimator.coef_.tolist(),
            "intercept": float(estimator.intercept_),
            "feature_names": model.pipeline.named_steps["preprocess"]
            .get_feature_names_out()
            .tolist(),
        },
    )
    lines = [
        "# R1 final evaluation",
        "",
        "Period: March 12-April 1, 2023 (Europe/Berlin).",
        f"Ridge alpha: {alpha:g}. Seasonal reference: {reference}.",
        f"One final Ridge fit: January 8-March 11; {model.training_rows} rows. No refitting during evaluation.",
        "",
        "| Model | MAE | RMSE | Bias | Successful / planned | DST substitutions |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, values in metrics.items():
        formatted = [
            "undefined" if values[key] is None else f"{values[key]:.6f}"
            for key in ("mae", "rmse", "bias")
        ]
        lines.append(
            f"| {name} | {' | '.join(formatted)} | {coverage[name]['successful']} / 503 | {coverage[name]['substituted_predictions']} |"
        )
    lines.extend(
        [
            "",
            "Errors are duration-weighted, in EUR/MWh; bias is prediction minus actual.",
            f"Common scored intervals: {len(common)}. Coverage gate passed: {passed}.",
            "Ridge skill versus the frozen reference: "
            + ("undefined." if skill is None else f"{skill:.2%}."),
            f"High-price threshold: {threshold:.6f} EUR/MWh (initial training 95th percentile).",
            "",
            "This is a short latest-vintage historical benchmark. Historical publication and revision",
            "availability are unverified. Results are descriptive, with no significance or general-superiority claim.",
            "The saved selections were not retuned after final scoring. Validation reports did not originally",
            "record snapshot hashes; this run captures their bytes and the current verified dataset together.",
            "",
            "See metrics.json for daily/month/hour/event breakdowns, predictions.json for interval errors",
            "and lag provenance, model.json for fitted parameters, and manifest.json for source/output hashes.",
            "",
        ]
    )
    lines.extend([
        "## Synthetic merit-order examples", "",
        "| Case | Demand MW | Hours | Price EUR/MWh | Delivered MWh | Unmet MWh |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for case in dispatch["cases"]:
        market = case["result"]
        lines.append(f"| {case['case_id']} | {case['demand_mw']:g} | {case['duration_hours']:g} | {market['clearing_price_per_mwh']:g} | {market['cleared_energy_mwh']:g} | {market['unmet_energy_mwh']:g} |")
    lines.extend(["", dispatch["shortage_policy"], "", dispatch["limitations"],
                  "", "See dispatch.json for generator offers, dispatch, and per-generator operating profits.", ""])
    if (input_dir / "ATTRIBUTION.md").is_file():
        (output / "ATTRIBUTION.md").write_bytes((input_dir / "ATTRIBUTION.md").read_bytes())
        lines.extend(["Data attribution and recorded licensing: see ATTRIBUTION.md.", ""])
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    # Preserve exact source/config/selection bytes, including uncommitted work.
    sources = {
        Path("src/gridquant") / path.relative_to(PACKAGE_DIR): path
        for path in sorted(PACKAGE_DIR.rglob("*.py"))
    }
    for relative_name in (
        "final_evaluation.py",
        "ridge_validation.py",
        "seasonal_validation.py",
        "configs/r1.yaml",
        "docs/r1_protocol.md",
        "pyproject.toml",
        "uv.lock",
        "reports/ridge_validation.json",
        "reports/seasonal_validation.json",
        BUNDLE_MANIFEST,
        "ATTRIBUTION.md",
    ):
        candidate = input_dir / relative_name
        if candidate.is_file():
            sources[Path(relative_name)] = candidate
    sources[raw_manifest_path.relative_to(input_dir)] = raw_manifest_path
    source_hashes = {}
    for relative, source in sources.items():
        saved = output / "source" / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(source.read_bytes())
        source_hashes[relative.as_posix()] = sha256(saved)
    # Git describes the executing source checkout, not a relocated input bundle.
    # Installed packages need no Git executable or repository to reproduce results.
    git_revision: str | None = None
    git_dirty: bool | None = None
    source_root = PACKAGE_DIR.parent.parent
    if PACKAGE_DIR.parent.name == "src" and (source_root / ".git").exists():
        try:
            revision = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=source_root,
                capture_output=True,
                text=True,
                check=False,
            )
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=source_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if revision.returncode == status.returncode == 0:
                git_revision = revision.stdout.strip()
                git_dirty = bool(status.stdout.strip())
        except OSError:
            pass  # Exact source bytes remain archived even when Git is unavailable.
    write_json(
        output / "manifest.json",
        {
            "created_at_utc": datetime.now(UTC),
            "experiment_id": EXPERIMENT,
            "git_revision": git_revision,
            "git_dirty": git_dirty,
            "offline": True,
            "source_archive_sha256": source_hashes,
            "input_sha256": {
                path.relative_to(input_dir).as_posix(): sha256(path)
                for path in provenance_paths
            },
            "output_sha256": {
                path.name: sha256(path)
                for path in sorted(output.iterdir())
                if path.is_file()
            },
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": {
                name: version(name)
                for name in ("numpy", "scipy", "scikit-learn", "pyarrow", "pyyaml")
            },
            "elapsed_seconds": time.perf_counter() - started,
            "selection_evidence_limitation": "Validation reports originally omitted source/config hashes; their archived bytes are preserved here.",
        },
    )
    if not passed:
        raise ValueError("Forecast failures block release; inspect saved diagnostics.")
    return DemoResult(output_dir=output, summary=summary)
