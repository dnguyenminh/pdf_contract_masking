from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import ttfonts
from reportlab.pdfbase import pdfmetrics
import os

lines = [
"Tên: Lê Thị C",
"Số CMND: 012345678",
"Số CMND: 123456789012",
"Số điện thoại: 0912345678",
"Số điện thoại: 84912345678",
"Khoản vay: 84912345678",
"Số tiền: 84912345678",
"Một số dòng chứa các dãy số không có nhãn trước:",
"Ghi chú: 0912987654",
"Ref: 001234567890",
"Số tham chiếu 84911223344",
"Mã: 55667788",
"Chuỗi: 1234567 890123 0912345678 0987654321",
"Vô hướng: 111222333444 555666777",
"Kết hợp tiếng Việt với ký tự đặc biệt và các chuỗi số:",
"Người liên hệ: Nguyễn Văn D - số: 0912345678; mã KH: 99887766",
"Ghi chú nội bộ: CMND 321098765 (không có tiền tố Số CMND:)",
"Đường dây nóng: 84911223344; liên lạc: 0912000111",
"Số hợp đồng: HĐ-2025-00123, tham chiếu: 123456789012",
"Dòng kiểm tra cuối: 0912345678/123456789012 - 84912345678 | 000111222333",
]

os.makedirs('contract', exist_ok=True)
font_path = os.path.join(os.getcwd(), 'fonts', 'NotoSans-Regular.ttf')
font_name = None
if os.path.exists(font_path):
    try:
        ttf = ttfonts.TTFont('NotoExact', font_path)
        pdfmetrics.registerFont(ttf)
        font_name = 'NotoExact'
    except Exception:
        font_name = None

c = canvas.Canvas('contract/sample3.pdf', pagesize=letter)
width, height = letter
y = height - 72
body_font = font_name if font_name else 'Helvetica'

c.setFont(body_font, 12)
for line in lines:
    c.drawString(72, y, line)
    y -= 18
    if y < 72:
        c.showPage()
        y = height - 72
        c.setFont(body_font, 12)

c.showPage()
c.save()
print('Wrote contract/sample3.pdf')
