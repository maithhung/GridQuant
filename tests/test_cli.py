from typer.testing import CliRunner

from gridquant.cli import app

runner = CliRunner()


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Quantitative research toolkit for electricity markets." in result.stdout
