import fitz, traceback, os
p = os.path.join(os.getcwd(), 'hop_dong_da_che_AI_Final','che_42669366_10000009_[DN VAY VON KIEM HOP DONG TIN DUNG.pdf].pdf')
print('OPEN', p)
try:
    doc = fitz.open(p)
    print('DOC_OPENED')
    try:
        doc.apply_redactions()
        print('APPLY_OK')
    except Exception as e:
        print('APPLY_ERR', type(e), e)
        traceback.print_exc()
    doc.close()
except Exception as e:
    print('ERR', e)
    traceback.print_exc()
