# GridQuant

Reproducible short-term electricity market simulation and forecasting.

GridQuant is an early-stage Python toolkit for electricity-market research.
The current implementation provides an installable package, CLI help and
version output, a pure-Python merit-order calculator, and a basic Energy-Charts
price collector with JSON parsing and local storage. Broader simulation,
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

The CLI currently emits demonstration warning and error messages on startup,
including for successful help and version requests. Logging setup is unfinished.

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

## Development

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

Session 3 verification (2026-09-28): 64 tests and source type checking pass.
Six parser exception-type lint findings and one model-file formatting issue
remain; the project does not yet pass every quality gate.

Build the source distribution and wheel in `dist/`:

```sh
uv build
```

## Project Structure

```text
src/gridquant/
    __init__.py
    cli.py          CLI entry point and version option
    logging.py      Logging experiments; setup is unfinished
    merit_order.py  Generator offers, dispatch, and power/energy results
    collectors/energy_charts.py  Price fetching and JSON parsing
    data/models.py  Typed UTC price intervals
    data/storage.py  Manifest creation and raw-response storage
tests/
    test_cli.py     CLI help test
    test_merit_order.py  Calculator and output-unit tests
    test_energy_charts.py  Parser and time-coverage tests
    test_energy_charts_fetch.py  Offline HTTP tests
    test_storage.py  Manifest and storage tests
json_practice.py    Fetch/cache/parse demonstration
docs/data_sources.md  Source contract and attribution
pyproject.toml      Package metadata and development tools
uv.lock            Locked dependencies
```
