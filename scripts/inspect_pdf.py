import fitz
import os

pdf_path = 'contract/sample1.pdf'
font_path = 'fonts/NotoSans-Regular.ttf'

print('PDF:', pdf_path)
print('Exists:', os.path.exists(pdf_path))
print('Font file:', font_path, 'Exists:', os.path.exists(font_path))
if os.path.exists(font_path):
    print('Font size (bytes):', os.path.getsize(font_path))

try:
    doc = fitz.open(pdf_path)
    print('Pages:', doc.page_count)
    for i, page in enumerate(doc):
        print('\nPage', i)
        try:
            fonts = page.get_fonts()
            print('Fonts found on page (count):', len(fonts))
            for f in fonts:
                print('  ', f)
        except Exception as e:
            print('Error getting fonts:', e)
        text = page.get_text('text')
        print('\nExtracted text (raw):')
        print(text)
except Exception as e:
    print('Error opening PDF:', e)
