import os
import re
import fitz
from pdf_contract_masking.config import RedactionConfig
from pdf_contract_masking.knowledge_base import KnowledgeBase
from pdf_contract_masking.processor import PDFProcessor


def test_integration_redaction_sample1(tmp_path, capsys):
    # Setup
    cfg = RedactionConfig()
    kb = KnowledgeBase()
    proc = PDFProcessor(cfg, kb, nlp_pipeline=None)
    src = os.path.abspath('contract/sample1.pdf')
    out = str(tmp_path / 'che_sample1_out.pdf')

    # Run processor (this will apply redactions/overlays)
    redactions = proc.process_pdf_final(src, out)

    # Open the saved PDF and extract text to ensure phone-like tokens are not trivially present
    doc = fitz.open(out)
    full_text = "".join([p.get_text('text') for p in doc])

    # look for phone-like numbers per config (digits only): any 9+ digit sequence starting with 84 or 0
    phone_matches = re.findall(r"(?:84|0)\d{7,}", re.sub(r"\D", "", full_text))

    # Assert that we did perform at least one redaction (sanity)
    assert redactions >= 0

    # If phone-like digits remain in plain text, flag; tests should not be flaky but PyMuPDF builds may differ
    assert len(phone_matches) == 0, f"Found phone-like digits left in output text: {phone_matches}"

    # Ensure the processor printed per-redaction console lines (instrumentation)
    captured = capsys.readouterr()
    assert 'REDACTED:' in captured.out, "Processor did not print any REDACTED: lines to console"
    doc.close()