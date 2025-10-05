import sys

def main():
    print('Python:', sys.version)
    try:
        import fitz
        print('PyMuPDF (fitz) imported:', fitz.__doc__.splitlines()[0])
    except Exception as e:
        print('PyMuPDF import failed:', e)
    try:
        import transformers
        print('transformers version:', transformers.__version__)
    except Exception as e:
        print('transformers import failed:', e)
    try:
        import torch
        print('torch version:', torch.__version__)
        print('cuda available:', torch.cuda.is_available())
    except Exception as e:
        print('torch import failed:', e)
    try:
        from pdf_contract_masking import mask_text
        print('package import OK, mask_text sample:', mask_text('1234567890'))
    except Exception as e:
        print('package import failed:', e)

if __name__ == '__main__':
    main()
