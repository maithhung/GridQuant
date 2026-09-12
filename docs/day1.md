# make dir, file using bash
mkdir -p src/gridquant
touch pyproject.toml README.md
touch src/gridquant/__init__.py
touch src/gridquant/cli.py

# alternative way using powershell

mkdir src/gridquant
New-Item pyproject.toml
New-Item README.md
New-Item src/gridquant/__init__.py
New-Item src/gridquant/cli.py

uv init --package # inside root, else parse the project/package name
uv add typer

# from main.py to cli.py:
[project.scripts]
gridquant = "gridquant.cli:app" # instead of gridquant:main

gridquant
   ↓
gridquant.cli
   ↓
app

# Understanding cli.py

Parameters like name, help are parsed to the app, which are wrapped using callback.

# Add ruff and pytest

uv add --dev pytest ruff #only for developer

Ruff is for clean codecheck:

uv run ruff check .

pytest is to check if the code is running.

uv run pytest

                    Your Python project
                           │
             ┌─────────────┴─────────────┐
             │                           │
           Ruff                        pytest
             │                           │
      Static analysis                Execute code
             │                           │
      "Is this code                "Does this code
        written well?"                 work?"
             │                           │
      ┌──────┴──────┐             ┌──────┴──────┐
      │             │             │             │
   linting      formatting     unit tests   integration tests

   