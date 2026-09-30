from importlib.metadata import version

import typer

from gridquant.logging import configure_logging

app = typer.Typer(
    name="gridquant",
    help="Quantitative research toolkit for electricity markets.",
)


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"gridquant {version('gridquant')}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show the version of the package and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """GridQuant command-line interface."""
    configure_logging()


if __name__ == "__main__":
    app()
