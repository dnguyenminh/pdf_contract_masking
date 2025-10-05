from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os


def create_sample(path, font_path=None):
    """Create a sample PDF containing Vietnamese text.

    If `font_path` points to a Unicode TTF (e.g. Noto Sans), it will be embedded
    so Vietnamese characters render correctly. If no font is provided the PDF
    will be generated with the default font (may not support Vietnamese).
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    c = canvas.Canvas(path)

    font_name = None
    if font_path and os.path.exists(font_path):
        try:
            font_name = 'NotoSansCustom'
            pdfmetrics.registerFont(TTFont(font_name, font_path))
            c.setFont(font_name, 14)
        except Exception as e:
            print(f"Warning: failed to register font {font_path}: {e}")
            font_name = None

    if not font_name:
        # fallback to default (may not render Vietnamese correctly)
        c.setFont('Helvetica', 14)

    c.drawString(100, 750, "Hợp đồng bán hàng")
    c.drawString(100, 730, "Tên khách hàng: Nguyễn Văn A")
    c.drawString(100, 710, "Số CMND: 012345678")
    c.drawString(100, 690, "Số điện thoại: 0912345678")
    c.save()


if __name__ == '__main__':
    # By default look for a font at fonts/NotoSans-Regular.ttf
    default_font = os.path.join('fonts', 'NotoSans-Regular.ttf')
    if not os.path.exists(default_font):
        print('\nNote: fonts/NotoSans-Regular.ttf not found. Generated PDF may not render Vietnamese correctly.')
        print("To embed a Unicode font, download the Noto Sans TTF into ./fonts/ and run this script again.")
    create_sample('./contract/sample1.pdf', font_path=default_font if os.path.exists(default_font) else None)
    print('Sample PDF created at ./contract/sample1.pdf')
