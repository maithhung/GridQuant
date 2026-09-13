# GridQuant

Reproducible short-term electricity market simulation and forecasting.

GridQuant is an early-stage Python toolkit for electricity-market research.
The current implementation provides an installable package, CLI help and
version output, and development checks. Market-data collection, simulation,
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
tests/
    test_cli.py     CLI help test
pyproject.toml      Package metadata and development tools
uv.lock            Locked dependencies
```

