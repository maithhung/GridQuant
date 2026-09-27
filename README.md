# GridQuant

Reproducible short-term electricity market simulation and forecasting.

GridQuant is an early-stage Python toolkit for electricity-market research.
The current implementation provides an installable package, CLI help and
version output, a pure-Python merit-order calculator, and development checks.
Market-data collection, broader simulation, forecasting, and backtesting are planned.

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

The output API replaces `cleared_volume_mwh` / `delivered_volume_mwh` with
`cleared_volume_mw` / `cleared_energy_mwh`, and `unmet_demand_mwh` with
`unmet_demand_mw` / `unmet_energy_mwh`. Update callers to use the matching unit.

## Development

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

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
tests/
    test_cli.py     CLI help test
    test_merit_order.py  Calculator and output-unit tests
pyproject.toml      Package metadata and development tools
uv.lock            Locked dependencies
```
