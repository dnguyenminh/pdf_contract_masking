# Python environment for pdf_contract_masking

This repository requires Python 3.11. Two options are provided below depending on whether you have system Python 3.11 installed or are using Anaconda/Miniconda.

## Option A — Create a standard venv (requires system Python 3.11)
PowerShell:

```powershell
# Use the Windows Python launcher if available
py -3.11 -m venv .venv
# Activate
.\.venv\Scripts\Activate.ps1
# Verify
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip --version
```

CMD:

```cmd
py -3.11 -m venv .venv
.\.venv\Scripts\activate.bat
.\.venv\Scripts\python.exe --version
```

If `py` or `python3.11` is not available, install Python 3.11 from https://www.python.org/downloads/windows/ or use the Microsoft Store installer.

## Option B — Use Conda (Anaconda/Miniconda)
If you have Anaconda or Miniconda installed (detected on this system), create and use a conda env:

```powershell
# Create environment (only needs to be done once)
conda create -y -n pdf_contract_masking_py311 python=3.11
# Activate
conda activate pdf_contract_masking_py311
# Verify
python --version
python -m pip --version
```

On this machine, a project-local conda environment at `.conda_env` was created and verifies as Python 3.11.13. Use the project-local environment when working inside this repository.

## Project-local Conda environment
Create and activate the project-local environment (stored in the repository) with:

```powershell
# Create (already done):
conda create -y -p ./.conda_env python=3.11
# Activate in PowerShell:
conda activate C:\projects\python\pdf_contract_masking\.conda_env
# or using relative path from repo root:
conda activate ./.conda_env
# Verify:
conda run -p ./.conda_env python --version
conda run -p ./.conda_env python -m pip --version
```

### Recreate environment from environment.yml

You can recreate the same environment on another machine using `environment.yml`:

```powershell
# Create environment and install dependencies from environment.yml
conda env create -f environment.yml -p ./.conda_env
# Activate
conda activate ./.conda_env
# Verify
python --version
python -m pip --version
```

## Developer notes — running tests

The test suite imports the package from `src/`. You have two options to run tests locally:

1) Add `src/` to `PYTHONPATH` for the test run (no install needed):

```powershell
# From project root (PowerShell):
conda run -p ./.conda_env python -c "import sys; sys.path.insert(0, 'src'); import unittest; loader=unittest.TestLoader(); suite=loader.discover('tests'); import unittest; runner=unittest.TextTestRunner(verbosity=2); result=runner.run(suite); import sys as _s; _s.exit(0 if result.wasSuccessful() else 1)"
```

2) Or install the package editable into the environment and run tests normally:

```powershell
conda run -p ./.conda_env pip install -e .
conda run -p ./.conda_env python -m unittest discover -v
```

Either approach works; using editable install is closer to how CI runs tests.

## Notes
- If you prefer a `.venv` but don't have system Python 3.11, you can install it or use `pyenv`/`scoop`/`choco` to manage versions.
- After activating your chosen environment, install project dependencies (if any) with pip or conda.

## Vietnamese text rendering in sample PDFs

The repository includes a small script `create_sample_contract.py` which generates `./contract/sample1.pdf` used for testing. Many default PDF fonts do not include Vietnamese glyphs, which causes characters to appear incorrectly.

To ensure Vietnamese text renders correctly in generated PDFs:

1) Download a Unicode TTF such as Noto Sans (Regular) and place it in `./fonts/NotoSans-Regular.ttf`.
	- Noto Sans download: https://fonts.google.com/specimen/Noto+Sans

2) Run the sample generator (it will embed the font if found):

```powershell
python create_sample_contract.py
```

3) Re-run the main script to process the PDF:

```powershell
python src\pdf_contract_masking\contract_masking.py
```

If no font is present the generator falls back to a default font which may not render Vietnamese correctly (you will see missing or replaced characters). Embedding a Unicode TTF fixes this.
