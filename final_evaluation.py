"""Command-line wrapper for the reusable frozen final-evaluation workflow."""

import argparse
from pathlib import Path

from gridquant.demo import run_demo


def main() -> None:
    project_root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=project_root)
    parser.add_argument(
        "--output", type=Path, default=project_root / "reports/final_evaluation"
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        default=True,
        help="Use local inputs only (always enabled for this workflow).",
    )
    args = parser.parse_args()
    result = run_demo(
        input_dir=args.input_dir, output_dir=args.output, offline=args.offline
    )
    report = (result.output_dir / "report.md").read_text(encoding="utf-8")
    print("\n".join(report.splitlines()[:14]))
    print(f"Saved final evaluation: {result.output_dir}")


if __name__ == "__main__":
    main()
