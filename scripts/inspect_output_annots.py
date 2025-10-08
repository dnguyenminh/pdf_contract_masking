import fitz
import sys
p = sys.argv[1] if len(sys.argv) > 1 else r"hop_dong_da_che_AI_Final\che_42669366_10000009_[DN VAY VON KIEM HOP DONG TIN DUNG.pdf].pdf"
print('Inspecting', p)
doc = fitz.open(p)
print('pages=', len(doc))
for i, page in enumerate(doc):
    print(f'--- page {i} ---')
    try:
        annots = list(page.annots()) if page.first_annot else []
    except Exception as e:
        annots = []
    print('annots count=', len(annots))
    for a in annots:
        try:
            print('annot:', a.type[0], 'rect=', a.rect, 'info=', {k: a.info.get(k) for k in a.info})
        except Exception as e:
            print('annot enumerate failed', e)
    try:
        txt = page.get_text('text')
        print('text sample:', repr(txt).strip()[:200])
    except Exception as e:
        print('get_text failed', e)
    try:
        blocks = page.get_text('blocks')
        print('blocks count=', len(blocks))
        # print first few blocks
        for b in blocks[:5]:
            r = fitz.Rect(b[:4])
            s = b[4].strip()
            print(' block rect=', r, 'text=', repr(s)[:100])
    except Exception as e:
        print('get_text blocks failed', e)

    # try to find our phone tokens via regex in text
    import re
    phones = re.findall(r"(\b(?:84|0)\d{9}\b)", txt)
    print('phones found in text:', phones)

print('done')
