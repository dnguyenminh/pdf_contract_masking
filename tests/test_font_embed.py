import os
import pytest
import fitz

from tests.pdf_helpers import make_sample_pdf


def try_download_font():
    try:
        from scripts.get_noto import download_noto
        return download_noto()
    except Exception:
        return None


def test_pdf_embeds_noto_when_available(tmp_path):
    # Try to ensure the font is present; if not available (network blocked), skip embedding assertion
    font_path = os.path.join(os.getcwd(), 'fonts', 'NotoSans-Regular.ttf')
    if not os.path.exists(font_path):
        try:
            font_path = try_download_font()
        except Exception:
            font_path = None

    pdf_path = tmp_path / 'sample_font_test.pdf'
    make_sample_pdf(str(pdf_path), '111222333444', '0912345678', cust_name='Phạm Văn T')

    doc = fitz.open(str(pdf_path))
    # If the font file is not present, try to download it; if that fails, the test should fail
    if not font_path or not os.path.exists(font_path):
        raise AssertionError('Noto Sans TTF not available and downloader failed; cannot assert embedding')

    # Inspect fonts on first page
    page = doc[0]
    fonts = page.get_fonts() or []
    doc.close()

    # Ensure at least one embedded font name contains 'Noto' (case-insensitive)
    found = any(('noto' in (str(f).lower())) for f in fonts)
    assert found, f'No Noto font found in PDF fonts: {fonts}'
