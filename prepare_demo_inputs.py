"""Prepare the frozen R1 input bundle without downloads or overwrites."""

import argparse
from pathlib import Path

import yaml

from gridquant.demo import check_config, load_selections
from gridquant.demo_bundle import prepare_bundle


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=root)
    parser.add_argument("--output", type=Path, default=root / "demo_inputs")
    args = parser.parse_args()
    source = args.source_dir.resolve()
    config = yaml.safe_load((source / "configs/r1.yaml").read_text(encoding="utf-8"))
    check_config(config)
    load_selections(config, input_dir=source)
    bundle = prepare_bundle(source_dir=source, output_dir=args.output)
    print(f"Prepared verified input bundle: {bundle}")


if __name__ == "__main__":
    main()
