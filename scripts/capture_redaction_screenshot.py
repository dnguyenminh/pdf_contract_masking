import os
import re
import fitz
from pdf_contract_masking.constants import PHONE_REGEX

# Path to the processed PDF
pdf_path = os.path.join(os.getcwd(), 'hop_dong_da_che_AI_Final', 'che_42669366_10000009_[DN VAY VON KIEM HOP DONG TIN DUNG.pdf].pdf')
out_dir = os.path.join(os.getcwd(), 'screenshots')
os.makedirs(out_dir, exist_ok=True)

if not os.path.exists(pdf_path):
    print('MISSING_PDF', pdf_path)
    raise SystemExit(1)

doc = fitz.open(pdf_path)
print('PAGES', len(doc))

found = 0
for pnum, page in enumerate(doc):
    text = page.get_text('text')
    for m in PHONE_REGEX.finditer(text):
        token = m.group(0)
        areas = page.search_for(token)
        if not areas:
            continue
        for idx, area in enumerate(areas):
            # render page at higher resolution
            scale = 2.0
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat)
            # compute scaled bbox
            x0 = int(area.x0 * scale)
            y0 = int(area.y0 * scale)
            x1 = int(area.x1 * scale)
            y1 = int(area.y1 * scale)
            pad = int(10 * scale)
            bx0 = max(0, x0 - pad)
            by0 = max(0, y0 - pad)
            bx1 = min(pix.width, x1 + pad)
            by1 = min(pix.height, y1 + pad)
            img_bytes = pix.tobytes("png")
            # try to use PIL to crop and draw box
            try:
                from PIL import Image, ImageDraw
                from io import BytesIO
                im = Image.open(BytesIO(img_bytes))
                draw = ImageDraw.Draw(im)
                # draw rectangle (red) around token
                draw.rectangle([x0, y0, x1, y1], outline=(255, 0, 0), width=3)
                cropped = im.crop((bx0, by0, bx1, by1))
                out_name = f'phone_p{pnum}_{token}_{idx}.png'
                out_path = os.path.join(out_dir, out_name)
                cropped.save(out_path)
                print('SAVED', out_path)
                found += 1
            except Exception:
                # fallback: save full page image
                out_name = f'page_p{pnum}_token_{token}_{idx}.png'
                out_path = os.path.join(out_dir, out_name)
                with open(out_path, 'wb') as fh:
                    fh.write(img_bytes)
                print('SAVED_FULLPAGE', out_path)
                found += 1

print('FOUND', found)
