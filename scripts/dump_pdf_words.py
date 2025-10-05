import fitz
import sys
p = 'contract/sample1.pdf'
try:
    doc = fitz.open(p)
except Exception as e:
    print('Could not open', p, e)
    sys.exit(1)
for i, page in enumerate(doc):
    print(f'--- Page {i} text ---')
    txt = page.get_text('text')
    print(txt)
    print('--- Page words (x0,y0,x1,y1,word) ---')
    words = page.get_text('words')
    for w in words:
        print(repr(w[4]), w[0], w[1], w[2], w[3])
    print('\n')
