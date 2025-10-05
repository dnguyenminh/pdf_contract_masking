from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import ttfonts
from reportlab.pdfbase import pdfmetrics
import os


def make_sample_pdf(path: str, cmnd: str, phone: str, cust_name: str = 'Nguyễn Văn A'):
    """Create a simple sample PDF. If a TTF exists at ./fonts/NotoSans-Regular.ttf,
    register and embed it so Vietnamese glyphs render correctly. Otherwise fall
    back to Helvetica (may not render Vietnamese accents).
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    width, height = letter

    # try to register NotoSans if present
    font_path = os.path.join(os.getcwd(), 'fonts', 'NotoSans-Regular.ttf')
    font_name = None
    if os.path.exists(font_path):
        try:
            ttf = ttfonts.TTFont('NotoSansCustom', font_path)
            pdfmetrics.registerFont(ttf)
            font_name = 'NotoSansCustom'
        except Exception:
            font_name = None

    c = canvas.Canvas(path, pagesize=letter)
    y = height - 72

    title_font = font_name if font_name else 'Helvetica'
    body_font = font_name if font_name else 'Helvetica'

    c.setFont(title_font, 18)
    c.drawString(72, y, 'Hợp đồng bán hàng')
    y -= 36
    c.setFont(body_font, 14)
    c.drawString(72, y, f'Tên khách hàng: {cust_name}')
    y -= 28
    c.drawString(72, y, f'Số CMND: {cmnd}')
    y -= 28
    c.drawString(72, y, f'Số điện thoại: {phone}')
    c.showPage()
    c.save()
    return path


def make_complex_pdf(path: str):
    """Create a PDF containing multiple labeled and unlabeled CMND and phone numbers,
    varied Vietnamese text, and random numeric noise to exercise detection rules.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    width, height = letter

    # try to register NotoSans if present
    font_path = os.path.join(os.getcwd(), 'fonts', 'NotoSans-Regular.ttf')
    font_name = None
    if os.path.exists(font_path):
        try:
            ttf = ttfonts.TTFont('NotoSansCustom', font_path)
            pdfmetrics.registerFont(ttf)
            font_name = 'NotoSansCustom'
        except Exception:
            font_name = None

    c = canvas.Canvas(path, pagesize=letter)
    y = height - 72
    title_font = font_name if font_name else 'Helvetica'
    body_font = font_name if font_name else 'Helvetica'

    c.setFont(title_font, 18)
    c.drawString(72, y, 'Danh sách kiểm tra hợp đồng - Tài liệu kiểm thử')
    y -= 36
    c.setFont(body_font, 12)

    # Labeled examples
    examples = [
        'Tên: Lê Thị C',
        'Số CMND: 012345678',
        'Số CMND: 123456789012',
        'Số điện thoại: 0912345678',
        'Số điện thoại: 84912345678',
    ]
    for ex in examples:
        c.drawString(72, y, ex)
        y -= 18

    y -= 8
    c.drawString(72, y, 'Một số dòng chứa các dãy số không có nhãn trước:')
    y -= 18

    # Unlabeled numeric noise and phone-like/id-like numbers
    noise = [
        'Ghi chú: 0912987654',
        'Ref: 001234567890',
        'Số tham chiếu 84911223344',
        'Mã: 55667788',
        'Chuỗi: 1234567 890123 0912345678 0987654321',
        'Vô hướng: 111222333444 555666777',
    ]
    for n in noise:
        c.drawString(72, y, n)
        y -= 16

    y -= 8
    c.drawString(72, y, 'Kết hợp tiếng Việt với ký tự đặc biệt và các chuỗi số:')
    y -= 18

    mixed = (
        'Người liên hệ: Nguyễn Văn D - số: 0912345678; mã KH: 99887766',
        'Ghi chú nội bộ: CMND 321098765 (không có tiền tố Số CMND:)',
        'Đường dây nóng: 84911223344; liên lạc: 0912000111',
        'Số hợp đồng: HĐ-2025-00123, tham chiếu: 123456789012',
    )
    for m in mixed:
        c.drawString(72, y, m)
        y -= 16

    # Additional line with many digits and punctuation to stress regex/pipeline
    y -= 10
    c.drawString(72, y, 'Dòng kiểm tra cuối: 0912345678/123456789012 - 84912345678 | 000111222333')

    c.showPage()
    c.save()
    return path
