# GridQuant

Reproducible short-term electricity market simulation and forecasting.

GridQuant is an early-stage Python toolkit for electricity-market research.
The current implementation provides an installable package, CLI help and
version output, a pure-Python merit-order calculator, and a basic Energy-Charts
price collector with JSON parsing, typed datasets, Parquet storage, and
JSON/Markdown interval-start coverage reports. Broader simulation,
forecasting, and backtesting are planned.

## Setup

Requires Python 3.14 or newer and uv. From the repository root:

```sh
uv sync --locked
```

## Usage

```sh
uv run gridquant --help
uv run gridquant --version
```

Help, `--version`, and `-v` exit successfully with no stderr output. Importing
the package's CLI/logging modules does not emit messages or configure logging.
Command execution configures diagnostics on stderr without replacing existing
logging handlers.

## Merit-order calculator

```python
from gridquant.merit_order import GeneratorOffer, clear_market

offers = [GeneratorOffer("A", 50.0, 10.0), GeneratorOffer("B", 100.0, 40.0)]
result = clear_market(offers, demand_mw=120.0, duration_hours=0.25)
```

| Output | Unit | Example result |
| --- | --- | --- |
| `dispatch_mw` | MW per generator | A: 50, B: 70 |
| `cleared_volume_mw` | MW | 120 |
| `cleared_energy_mwh` | MWh | 30 |
| `unmet_demand_mw` | MW | 0 |
| `unmet_energy_mwh` | MWh | 0 |
| `clearing_price_per_mwh` | EUR/MWh | 40 |
| `operating_profit_eur` | EUR per generator | A: 375, B: 0 |

Power does not scale with duration; energy and operating profit do. During a
shortage, the highest marginal cost among dispatched generators sets the model
price, and unmet demand is reported. With no dispatch, price is `None`; profits
are zero for zero demand and `None` for positive unmet demand.


## Electricity-price example

From the repository root:

```powershell
uv run python json_practice.py
```

The example selects DE-LU prices for 2026-09-26. It verifies and reuses a saved
response/manifest pair when present; otherwise it downloads and saves one.
The saved sample produces `Parsed 96 intervals`. UTC starts/ends and prices in
EUR/MWh are printed for the first five records. Offline replay requires both
files in `data/raw/energy_charts/DE-LU/`; a missing cache triggers HTTP even if
uv itself was invoked with `--offline`.

The adapter provides `fetch_price_response(start_date, end_date)` and
`parse_price_response(raw_json)`. Storage helpers build manifests and save raw
bytes without overwriting existing files. Requests have a 30-second timeout;
retries, refresh, atomic writes, and revision storage are future work.

See the [source contract and attribution](docs/data_sources.md) and
[historical sample checks](reports/historical_sample_coverage.md).

### Normalized storage and coverage reports

The same example now writes a Parquet dataset under
`data/processed/energy_charts/DE-LU/` and matching JSON/Markdown reports under
`reports/quality/DE-LU/`, using the sample date range as the filename.
It checks that loading the Parquet file reproduces the original dataset.
Parquet support uses PyArrow, included in the locked dependencies.

```python
from datetime import date
from pathlib import Path

from gridquant.data.normalized import load_dataset, save_dataset
from gridquant.data.reporting import save_quality_reports

# dataset is the PriceDataset assembled from verified raw bytes and a manifest.
path = Path("data/processed/example.parquet")
save_dataset(path, dataset)
restored = load_dataset(path)
save_quality_reports(restored, date(2026, 9, 26), 15, Path("reports/example.json"))
```

Parquet stores UTC starts/ends, EUR/MWh prices, and bidding zones, plus embedded
source metadata, original retrieval time, raw hash, units, and schema/normalization
versions. Raw responses and their manifests remain the source evidence, including
request parameters and attribution. Loading Parquet does not reverify raw files.

Equal datasets and identical reports are reused on replay. Different content at
an existing output path raises an error; choose a new path for revised outputs.
Row order and duplicates are preserved. Writes are sequential, not atomic;
Parquet byte identity across library versions is not guaranteed.

Reports check **interval-start coverage only** against a Europe/Berlin calendar.
They list missing, duplicated, and unexpected starts. Coverage uses unique
matching starts; 100% alone does not imply a complete grid if extra rows exist.
Interval ends, price conflicts, ordering, and historical availability remain
outside this check. No forecasting eligibility is inferred from a passing report.

See the [implemented data contract](docs/data_contract.md) and
[example coverage report](reports/quality/DE-LU/2026-09-26_2026-09-26.md).
All four saved samples have normalized outputs and complete start grids.
The practice example is configured for one 15-minute delivery day; when using
the functions for hourly data, pass an expected interval length of 60 minutes.

Session 4 is complete for its agreed learning scope. Historical publication and
revision availability remain unverified; no availability filter is implemented.
Session 5 will use a latest-vintage historical benchmark unless additional
evidence supports stronger claims. A contiguous development dataset and a frozen
evaluation protocol are still needed before training; the four samples alone
are insufficient. See the [availability decision](docs/data_sources.md).

## Development

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run python -m pytest
```

Session 5 Step 1 verification (2026-09-30): 96 tests pass, mypy passes all
12 source files, and Ruff lint and formatting pass. Tests exercise the installed
CLI in fresh processes, quiet imports, and diagnostics on stderr. A fresh wheel
installation outside the repository remains a later release check; this is not
an R1 release.

Build the source distribution and wheel in `dist/`:

```sh
uv build
```

## Project Structure

```text
src/gridquant/
    __init__.py
    cli.py          CLI entry point and version option
    logging.py      CLI diagnostic configuration; quiet on import
    merit_order.py  Generator offers, dispatch, and power/energy results
    collectors/energy_charts.py  Price fetching and JSON parsing
    data/models.py  Price intervals, source metadata, dataset container
    data/storage.py  Manifest creation and raw-response storage
    data/quality.py  One-day Berlin interval-start coverage
    data/normalized.py  Parquet save/load with embedded provenance
    data/reporting.py  JSON and Markdown coverage reports
tests/
    test_cli.py     Fresh-process help/version, quiet imports, stderr diagnostics
    test_merit_order.py  Calculator and output-unit tests
    test_energy_charts.py  Parser and time-coverage tests
    test_energy_charts_fetch.py  Offline HTTP tests
    test_storage.py  Manifest and storage tests
    test_quality.py  Coverage and DST tests
    test_normalized_reporting.py  Storage round trips and report tests
json_practice.py    Fetch/cache/parse, Parquet, and reporting demonstration
docs/data_sources.md  Source contract and attribution
docs/data_contract.md  Implemented dataset, storage, and reporting contract
pyproject.toml      Package metadata and development tools
uv.lock            Locked dependencies
```
