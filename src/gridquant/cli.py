import typer
from importlib.metadata import version
app = typer.Typer(
    name="gridquant",
    help="Quantitative research toolkit for electricity markets.",
)


@app.command()
def hello() -> None:
    """Test the GridQuant CLI."""
    typer.echo("Hello from GridQuant!")

def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"gridquant {version('gridquant')}")
        raise typer.Exit()

@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        help="Show the version of the package and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """GridQuant command-line interface."""

if __name__ == "__main__":
    app()
