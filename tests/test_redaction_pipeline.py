import os
import json
import re
import shutil
import fitz
import subprocess
from pathlib import Path

import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src' / 'pdf_contract_masking' / 'contract_masking.py'
OUT_DIR = ROOT / 'tests' / 'out'

# dynamically load the test helper module (avoids relative import issues when pytest
# collects tests from the project root)
spec = importlib.util.spec_from_file_location("pdf_helpers", str(ROOT / 'tests' / 'pdf_helpers.py'))
pdf_helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pdf_helpers)
make_sample_pdf = pdf_helpers.make_sample_pdf

def run_pipeline():
    env = os.environ.copy()
    env['RULES_ONLY'] = '1'
    # ensure subprocess uses same python interpreter as the test runner to avoid
    # environment/encoding mismatches; force UTF-8 output for subprocess
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    cmd = [sys.executable, str(SRC)]
    subprocess.check_call(cmd, env=env, cwd=str(ROOT))

def inspect_drawings(pdf_path):
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    draws = page.get_drawings()
    return draws

def test_partial_redaction_and_kb(tmp_path):
    # prepare
    inp = tmp_path / 'contract'
    out = tmp_path / 'hop_dong_da_che_AI_Final'
    inp.mkdir()
    # create sample PDFs with different lengths
    pdf1 = make_sample_pdf(str(inp / 'sample1.pdf'), '012345678', '0912345678')
    pdf2 = make_sample_pdf(str(inp / 'sample2.pdf'), '123456789012', '84912345678')
    # copy to project contract folder
    proj_contract = ROOT / 'contract'
    if proj_contract.exists():
        shutil.rmtree(proj_contract)
    shutil.copytree(str(inp), str(proj_contract))

    # ensure clean KB
    kb = ROOT / 'customer_redaction_rules.json'
    if kb.exists():
        kb.unlink()

    # run pipeline
    run_pipeline()

    # check outputs
    out_pdf = ROOT / 'hop_dong_da_che_AI_Final' / 'che_sample1.pdf'
    assert out_pdf.exists()

    # inspect drawings: should be >0
    draws = inspect_drawings(out_pdf)
    assert len(draws) > 0

    # KB should exist and not contain raw digits
    assert kb.exists()
    data = json.loads(kb.read_text(encoding='utf-8'))
    # KB keys are fingerprints (hex) - allowed to contain digits. We must ensure
    # that stored anchors do NOT contain raw digit sequences (PII). Patterns may
    # contain regex quantifiers like '\\d{9}' which include digits; those are
    # allowed. So check only the 'anchor' field inside rules.
    for fp, rules in data.items():
        for r in rules:
            anchor = r.get('anchor', '') or ''
            # no literal long digit sequences in anchor
            assert not re.search(r"\d{6,}", anchor), f"Anchor contains raw digits: {anchor}"
