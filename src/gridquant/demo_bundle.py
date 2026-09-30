"""Prepare and verify a relocatable bundle of saved R1 demonstration inputs."""

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

BUNDLE_MANIFEST = "bundle_manifest.json"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_file(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or ".." in Path(relative).parts or not path.is_relative_to(root.resolve()):
        raise ValueError(f"Bundle path must stay inside its directory: {relative}")
    if not path.is_file():
        raise FileNotFoundError(f"Offline input is missing: {path}")
    return path


def verify_bundle(input_dir: Path) -> dict[str, Any]:
    """Verify every inventoried file; the inventory is integrity, not authenticity."""
    root = input_dir.resolve()
    manifest = json.loads(local_file(root, BUNDLE_MANIFEST).read_text(encoding="utf-8"))
    if manifest.get("bundle_schema_version") != 1 or manifest.get("experiment_id") != "r1_hourly_2023_v1":
        raise ValueError("Unsupported demo bundle manifest.")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("Bundle manifest must list its files.")
    for name, record in files.items():
        path = local_file(root, name)
        if path.stat().st_size != record["bytes"] or file_sha256(path) != record["sha256"]:
            raise ValueError(f"Bundle integrity mismatch: {name}")
    return dict(manifest)


def verify_raw_manifest(input_dir: Path, config: dict[str, Any]) -> Path:
    """Verify the original request and licensing metadata alongside its bytes."""
    root = input_dir.resolve()
    raw = local_file(root, config["data"]["raw_path"])
    manifest_path = local_file(root, raw.with_suffix(".manifest.json").relative_to(root).as_posix())
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("endpoint") != "https://api.energy-charts.info/v2/price"
            or manifest.get("source") != "Energy-Charts"
            or manifest.get("parameters") != {"bzn": "DE-LU", "start": "2023-01-01", "end": "2023-04-01"}
            or manifest.get("raw_sha256", "").lower() != file_sha256(raw)):
        raise ValueError("Raw manifest does not match the frozen request and response.")
    if not isinstance(manifest.get("license"), str) or not manifest["license"].strip():
        raise ValueError("Raw manifest must preserve source license/attribution.")
    return manifest_path


def prepare_bundle(*, source_dir: Path, output_dir: Path) -> Path:
    """Copy preserved inputs into a new directory; never fetch or overwrite."""
    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"Bundle already exists; refusing overwrite: {output_dir}")
    config = yaml.safe_load(local_file(source_dir, "configs/r1.yaml").read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("experiment_id") != "r1_hourly_2023_v1":
        raise ValueError("Expected the frozen R1 configuration.")
    raw = local_file(source_dir, config["data"]["raw_path"])
    processed = local_file(source_dir, config["data"]["processed_path"])
    for path, key in ((raw, "raw_sha256"), (processed, "processed_sha256")):
        if file_sha256(path) != config["data"][key].lower():
            raise ValueError(f"Snapshot hash mismatch: {path}")
    raw_manifest = verify_raw_manifest(source_dir, config)
    manifest = json.loads(raw_manifest.read_text(encoding="utf-8"))
    names = [
        "configs/r1.yaml", config["data"]["raw_path"],
        raw_manifest.relative_to(source_dir).as_posix(), config["data"]["processed_path"],
        config["data"]["quality_report_path"], "reports/ridge_validation.json",
        "reports/seasonal_validation.json", "docs/r1_protocol.md", "docs/data_sources.md",
        "docs/data_contract.md", "pyproject.toml", "uv.lock",
    ]
    # Preflight every file before creating a partial output directory.
    payloads = {name: local_file(source_dir, name).read_bytes() for name in names}
    payloads["expected/forecast_metrics.json"] = local_file(source_dir, "reports/final_evaluation/metrics.json").read_bytes()
    attribution = (
        "# Demo data attribution\n\n"
        "Attribution: **Bundesnetzagentur | SMARD.de**.\n\n"
        "Acquired through Energy-Charts (Fraunhofer ISE), https://api.energy-charts.info/v2/price.\n\n"
        f"License recorded in the saved source manifest: {manifest['license']}\n\n"
        "License link: https://creativecommons.org/licenses/by/4.0/\n\n"
        "Source site: https://www.smard.de/\n\n"
        f"Original retrieval time: {manifest['retrieved_at_utc']}\n\n"
        "Data: DE-LU hourly day-ahead prices, January 1-April 1, 2023.\n\n"
        "Original JSON and its manifest are copied byte-for-byte. GridQuant's Parquet\n"
        "conversion preserves prices and normalizes timestamps to UTC; quality checks,\n"
        "forecasts, and evaluation reports are GridQuant transformations. No historical\n"
        "publication or revision availability is established. No source endorsement is implied.\n\n"
        "The three merit-order examples use explicitly synthetic generators and demand;\n"
        "they are independent of these market prices and are not a calibrated market model.\n"
    )
    readme = (
        "# GridQuant R1 local input bundle\n\n"
        "This directory contains frozen inputs, not an installed application.\n"
        "Keep its relative paths intact; it can be moved independently of the repository.\n\n"
        "From the project, after installing dependencies:\n\n"
        "```sh\nuv run python final_evaluation.py --input-dir demo_inputs --output outputs/demo --offline\n```\n\n"
        "The wrapper loads this bundle; it never downloads missing data. Output must be new.\n"
        "The bundle manifest hashes every included file except itself. Hashes detect changes\n"
        "relative to this inventory; they are not a digital signature or proof of source accuracy.\n\n"
        "See ATTRIBUTION.md for the saved data license and transformations. The config and\n"
        "validation reports freeze alpha 100 and the previous-day reference. The expected\n"
        "metrics are the already-inspected final result and are provided for reproduction,\n"
        "not further model selection. Actual historical availability remains unverified.\n\n"
        "The included lockfile and project metadata describe dependencies; they do not bundle\n"
        "Python or dependency wheels. A fresh installation may require network access.\n"
    )
    payloads["ATTRIBUTION.md"] = attribution.encode("utf-8")
    payloads["README.md"] = readme.encode("utf-8")
    inventory = {
        "bundle_schema_version": 1, "experiment_id": config["experiment_id"],
        "files": {name: {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
                  for name, content in sorted(payloads.items())},
    }
    output_dir.mkdir(parents=True)
    for name, content in payloads.items():
        destination = output_dir / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as output:
            output.write(content)
    with (output_dir / BUNDLE_MANIFEST).open("x", encoding="utf-8", newline="\n") as output:
        json.dump(inventory, output, indent=2, sort_keys=True)
        output.write("\n")
    verify_bundle(output_dir)
    return output_dir
