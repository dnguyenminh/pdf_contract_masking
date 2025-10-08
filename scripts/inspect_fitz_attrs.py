import fitz, os
p = os.path.join(os.getcwd(), 'hop_dong_da_che_AI_Final','che_42669366_10000009_[DN VAY VON KIEM HOP DONG TIN DUNG.pdf].pdf')
doc = fitz.open(p)
page = doc[0]
print('Document members containing redact/apply:')
for name in dir(doc):
    if 'redact' in name.lower() or 'apply' in name.lower():
        print('DOC:', name)
print('Page members containing redact/apply:')
for name in dir(page):
    if 'redact' in name.lower() or 'apply' in name.lower():
        print('PAGE:', name)
print('Done')
doc.close()
