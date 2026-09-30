import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gridquant.cli import app

runner = CliRunner()


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Quantitative research toolkit for electricity markets." in result.stdout
    assert result.stderr == ""


@pytest.mark.parametrize("option", ["--help", "--version", "-v"])
def test_installed_cli_in_fresh_process(option: str) -> None:
    command = Path(sys.executable).with_name(
        "gridquant.exe" if os.name == "nt" else "gridquant"
    )
    result = subprocess.run(
        [str(command), option], capture_output=True, text=True, timeout=15, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    if option == "--help":
        assert "Quantitative research toolkit for electricity markets." in result.stdout
    else:
        assert result.stdout.strip() == f"gridquant {version('gridquant')}"


def test_imports_do_not_emit_or_configure_logging() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import logging; "
                "root = logging.getLogger(); "
                "before = (root.level, list(root.handlers)); "
                "import gridquant.logging; import gridquant.cli; "
                "assert (root.level, root.handlers) == before"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


def test_cli_logging_writes_diagnostics_once_to_stderr() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import logging; "
                "from gridquant.cli import main; "
                "main(); main(); "
                "logging.getLogger('gridquant').warning('example diagnostic')"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == "WARNING: example diagnostic\n"
