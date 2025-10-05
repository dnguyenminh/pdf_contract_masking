import os
import json
import shutil
import fitz
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src' / 'pdf_contract_masking' / 'contract_masking.py'


def run_pipeline_for_sample3():
    env = os.environ.copy()
    env['RULES_ONLY'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    cmd = [env.get('PYTHON', 'python'), str(SRC)]
    subprocess.check_call(cmd, env=env, cwd=str(ROOT))


def inspect_drawings(pdf_path):
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    draws = page.get_drawings()
    doc.close()
    return draws


def test_pipeline_on_complex_sample(tmp_path):
    # Ensure contract folder contains sample3
    src_sample = ROOT / 'contract' / 'sample3.pdf'
    assert src_sample.exists(), f'sample3.pdf must exist at {src_sample}'

    # Count labeled tokens in the original PDF (we expect these to be redacted)
    doc_src = fitz.open(str(src_sample))
    src_text = doc_src[0].get_text('text')
    doc_src.close()
    id_pattern = re.compile(r"(?:Số\s*CMND[:\s]*|CMND[:\s]*)\s*(\d{9}|\d{12})", re.IGNORECASE)
    phone_pattern = re.compile(r"(?:Số\s*điện\s*thoại[:\s]*|Số\s*điện thoại[:\s]*)\s*((?:84|0)\d{9})", re.IGNORECASE)
    labeled_ids = id_pattern.findall(src_text)
    labeled_phones = phone_pattern.findall(src_text)
    labeled_count = len(labeled_ids) + len(labeled_phones)

    # Ensure old outputs and KB are removed
    out_dir = ROOT / 'hop_dong_da_che_AI_Final'
    if out_dir.exists():
        shutil.rmtree(out_dir)
    kb = ROOT / 'customer_redaction_rules.json'
    if kb.exists():
        kb.unlink()

    # copy sample3 into ./contract (already located there, keep as-is)

    # run pipeline (rules-only)
    run_pipeline_for_sample3()

    # output PDF should exist
    out_pdf = out_dir / 'che_sample3.pdf'
    assert out_pdf.exists(), 'Redacted output PDF not produced'

    # drawings should be present
    draws = inspect_drawings(out_pdf)
    assert len(draws) > 0, 'No drawing (redaction) objects found on output PDF'

    # At minimum the pipeline should have redacted all explicitly labeled tokens
    assert len(draws) >= labeled_count, (
        f'Expected at least {labeled_count} redaction drawings (for labeled tokens), found {len(draws)}'
    )

    # KB should exist and not contain raw long digit sequences in anchors
    assert kb.exists(), 'Knowledge base not created'
    data = json.loads(kb.read_text(encoding='utf-8'))
    # anchors sanitized
    for fp, rules in data.items():
        for r in rules:
            anchor = r.get('anchor', '') or ''
            assert not __import__('re').search(r"\d{6,}", anchor), f'Anchor contains raw digits: {anchor}'

    # basic smoke: ensure at least 3 redactions were recorded (heuristic)
    assert len(draws) >= 3, f'Expected >=3 redaction drawings, found {len(draws)}'
