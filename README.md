# GridQuant

Reproducible short-term electricity market simulation and forecasting.

GridQuant is an early-stage Python toolkit for reproducible electricity-market research. The current implementation provides an installable package, CLI help and version output, a pure-Python merit-order calculator with reproducible synthetic example scenarios, and an Energy-Charts price-data pipeline with JSON parsing, typed datasets, Parquet storage, and coverage reporting. Hourly seasonal forecasting baselines, a Ridge forecasting pipeline, validation selection, and a frozen R1 final evaluation are also implemented. Broader market simulation and backtesting remain planned.


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

### Merit-order example inputs

Three synthetic merit-order scenarios are provided under `examples/merit_order/`:

* `basic.json` — normal market clearing with partial dispatch of the marginal generator.
* `negative_price.json` — demonstrates that negative marginal-cost offers are supported.
* `shortage.json` — demonstrates insufficient available capacity and explicit unmet demand.

These files contain only synthetic generator offers, demand, and delivery-period duration. They are intended as reproducible inputs for the pure-Python merit-order calculator.

Example:

```python
from pathlib import Path

from gridquant.merit_order import clear_market
from gridquant.merit_order_io import load_merit_order_case

case = load_merit_order_case(
    Path("examples/merit_order/basic.json")
)

result = clear_market(
    case.generators,
    demand_mw=case.demand_mw,
    duration_hours=case.duration_hours,
)

print(result.dispatch_mw)
print(result.clearing_price_per_mwh)
```

The `basic.json` case corresponds to the worked example above:

```text
dispatch_mw = {"A": 50.0, "B": 70.0}
cleared_volume_mw = 120.0
cleared_energy_mwh = 30.0
clearing_price_per_mwh = 40.0
operating_profit_eur = {"A": 375.0, "B": 0.0}
```

The JSON examples are also included in the generated demo input bundle so that the market-clearing examples can be reproduced without depending on files outside the bundle.


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
evidence supports stronger claims. The contiguous 2023 development snapshot and
[R1 protocol](docs/r1_protocol.md) now define the seasonal-model experiment.
See the [availability decision](docs/data_sources.md) for its evidence limits.

## Seasonal price forecasts

Use a saved hourly dataset to forecast a complete Berlin delivery day:

```python
from datetime import date
from pathlib import Path

from gridquant.data.normalized import load_dataset
from gridquant.models.seasonal import forecast_seasonal

dataset = load_dataset(
    Path("data/processed/energy_charts/DE-LU/2023-01-01_2023-04-01.parquet")
)
previous_day = forecast_seasonal(dataset, date(2023, 2, 19), lag_days=1)
previous_week = forecast_seasonal(dataset, date(2023, 2, 19), lag_days=7)
print(previous_day[0])
```

Targets are generated from the calendar, so target-day prices are not needed.
Each `SeasonalPrediction` records the UTC origin and target interval, local hour
and repeated-hour occurrence, prediction, source day/UTC starts, source document
and hash, substitution, and failure reason. These aligned predictions can also
supply Ridge's two lag features. No model fitting or file writing occurs here.

Forecast issuance is 11:00 Berlin on D-1. Under the frozen latest-vintage
assumption, the complete D-1 price curve is usable, including its later hours.
Historical publication availability is not verified. Only lag days 1 and 7 are
supported; invalid arguments and naive input timestamps raise exceptions.

The source day must pass hourly validation, including its complete 23/24/25-hour
calendar, chronological order, durations, zone, and finite prices. Missing or
invalid curves return a failed prediction for every target instead of dropping
rows. A missing repeated-hour occurrence uses the available same-hour occurrence;
an hour absent because of spring DST uses the complete source-day mean. Both
substitutions are flagged, and mean predictions list every contributing start.

## Ridge price forecasts

Ridge reuses seasonal alignment for its two price lags and adds local hour,
weekday, and repeated-hour occurrence. Fit a single protocol alpha, then predict
a later day:

```python
from datetime import date

from gridquant.models.ridge import fit_ridge, forecast_ridge

# dataset is the saved PriceDataset loaded in the seasonal example above.
model = fit_ridge(dataset, date(2023, 1, 8), date(2023, 2, 18), alpha=1.0)
predictions = forecast_ridge(model, dataset, date(2023, 2, 19))
```

This example uses alpha 1.0 as a smoke check, not a validation-selected value.
`build_ridge_features(dataset, delivery_date)` exposes the same inputs and lag
provenance without attaching actual target prices. Training validates complete
hourly target days and fails on missing lag inputs. Prediction retains a failure
record for each target with invalid source data. Target prices are never needed
for prediction; the forecast day must be later than the last training target day.

The scikit-learn pipeline fits `StandardScaler` on the two training price columns
and fixed-category one-hot encoding on the calendar columns, followed by Ridge
with an intercept and deterministic SVD solver. Forecasting never refits this
pipeline. Supported alphas are 0.1, 1, 10, and 100. The fitted model records
training dates, row count, alpha, and source identity; predictions retain both
seasonal dependencies and their substitution flags. Historical availability
remains assumed. The validation scripts select parameters; the final evaluation
runner below verifies those saved choices and never tunes on final scores.

## Frozen final evaluation

```sh
uv run python final_evaluation.py
```

`final_evaluation.py` is now a thin argument-parsing/display wrapper around
`gridquant.demo.run_demo`. The reusable function accepts explicit paths and
returns a `DemoResult` with `output_dir` and `summary`, without printing:

```python
from pathlib import Path

from gridquant.demo import run_demo

result = run_demo(
    input_dir=Path("demo_inputs"),
    output_dir=Path("outputs/demo"),
    offline=True,
)
print(result.summary["metrics_eur_per_mwh"])
```

At this stage the input folder must preserve the existing relative layout:
`configs/r1.yaml`, the two `reports/*_validation.json` files, and the raw JSON
and Parquet at the paths named by the config. The repository itself can serve
as `input_dir`. A distributable input bundle and merit-order integration remain
the next steps; this function currently reproduces the forecasting workflow.
Only offline mode is supported. Missing input fails without a download, and
configured data paths must stay inside the supplied directory.

The wrapper accepts `--input-dir`, `--output`, and `--offline`, for example:

```sh
uv run python final_evaluation.py --input-dir demo_inputs --output outputs/demo --offline
```

Source preservation uses the executing package's Python files. Config/selection
files are archived from the supplied inputs; optional repository documents are
included when present. Git metadata is recorded when available and remains null
otherwise. Reproduction does not require the input bundle to be a Git checkout.

The runner checks the frozen `configs/r1.yaml`, dataset hashes, quality, and saved
validation choices. It refits Ridge once on January 8-March 11 with selected alpha
100, then scores all three models on March 12-April 1. It writes predictions,
MAE/RMSE/bias, coverage, DST substitutions, daily/month/hour/event breakdowns,
fitted parameters, a Markdown report, and a manifest with an exact source snapshot.
It uses saved data without downloading. High-price events use the initial training
95th percentile, not evaluation data.

The existing run is in [reports/final_evaluation/report.md](reports/final_evaluation/report.md).
All models produced 503/503 predictions. Ridge MAE is 27.185979 EUR/MWh versus
28.695400 for previous-day and 41.537594 for previous-week. Ridge's MAE reduction
against the frozen reference is 5.26%, but its positive bias is 17.129161 EUR/MWh.
This is a short descriptive latest-vintage result, not evidence of general superiority.

Existing output directories are never overwritten. For an intentional reproduction,
use `--output reports/final_evaluation_replay`; keep model choices fixed. Prediction
failures are saved and make the run exit unsuccessfully. Original validation reports
lacked snapshot hashes; the final manifest preserves their bytes together with the
current verified inputs, rather than claiming those hashes were recorded earlier.

## Development

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run python -m pytest
```

Workflow-extraction verification (2026-09-30): 155 tests pass, mypy passes all
18 source files, and Ruff lint and formatting pass. Tests cover seasonal
alignment, DST substitutions, invalid curves, provenance, training-only scaling,
constant features, target/future-price leakage, hand-calculated weighted metrics,
selection/config validation, and overwrite protection. A relocated minimal input
bundle reproduced metrics, predictions, fitted parameters, quality, and report
exactly with HTTP blocked, a different working directory, and Git unavailable.
The original final run was preserved. Final evaluation used one
fit on 1,512 rows and 503 target intervals per model. NumPy 2.5.3,
SciPy 1.18.1, and scikit-learn 1.9.1 are installed in the Python 3.14 environment.
Initial numerical-library imports were slow; routine checks now complete normally.
A fresh wheel
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
    models/seasonal.py  Previous-day/week forecasts with shared lag alignment
    models/ridge.py  Shared features, training-only Ridge pipeline, daily forecasts
    evaluation.py  Duration-weighted MAE, RMSE, bias, and reference skill
    demo.py  Reusable offline forecasting workflow with explicit input/output paths
tests/
    test_cli.py     Fresh-process help/version, quiet imports, stderr diagnostics
    test_merit_order.py  Calculator and output-unit tests
    test_energy_charts.py  Parser and time-coverage tests
    test_energy_charts_fetch.py  Offline HTTP tests
    test_storage.py  Manifest and storage tests
    test_quality.py  Coverage and DST tests
    test_normalized_reporting.py  Storage round trips and report tests
    test_seasonal.py  Seasonal alignment, DST, failures, and leakage
    test_ridge.py  Preprocessing, temporal boundaries, failures, and leakage
    test_evaluation.py  Independent weighted-metric hand calculations
    test_final_evaluation.py  Frozen settings, selections, overwrite protection
json_practice.py    Fetch/cache/parse, Parquet, and reporting demonstration
final_evaluation.py  Argument parsing and display for the reusable workflow
docs/data_sources.md  Source contract and attribution
docs/data_contract.md  Implemented dataset, storage, and reporting contract
pyproject.toml      Package metadata and development tools
uv.lock            Locked dependencies
```
## Reproducible demo input bundle

Create the frozen demo input bundle from the repository root:

```bash
uv run python prepare_demo_inputs.py
```

The command validates the configured inputs and creates `demo_inputs/` containing the files required for the reproducible forecasting and merit-order demonstrations.

The bundle includes, among other files:

```text
demo_inputs/
├── configs/
│   └── r1.yaml
├── data/
├── reports/
├── docs/
├── examples/
│   └── merit_order/
│       ├── basic.json
│       ├── negative_price.json
│       └── shortage.json
├── expected/
├── pyproject.toml
├── uv.lock
└── bundle_manifest.json
```

The merit-order files are synthetic demonstration inputs. The forecasting data retain their original source attribution and provenance information.

`bundle_manifest.json` records the packaged files and their hashes, allowing the prepared bundle to be checked for unexpected changes.

The bundle is generated rather than maintained manually. To rebuild it after changing one of the packaged inputs, remove the existing `demo_inputs/` directory and rerun:

```bash
uv run python prepare_demo_inputs.py
```
