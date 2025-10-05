import os
import urllib.request
import hashlib

FONT_URL = 'https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf'
TARGET_DIR = os.path.join(os.getcwd(), 'fonts')
TARGET_PATH = os.path.join(TARGET_DIR, 'NotoSans-Regular.ttf')


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def download_noto(force: bool = False):
    os.makedirs(TARGET_DIR, exist_ok=True)
    if os.path.exists(TARGET_PATH) and not force:
        print('Noto Sans already present at', TARGET_PATH)
        return TARGET_PATH
    print('Downloading Noto Sans from', FONT_URL)
    try:
        urllib.request.urlretrieve(FONT_URL, TARGET_PATH)
        print('Saved to', TARGET_PATH)
        return TARGET_PATH
    except Exception as e:
        # clean up partial download
        if os.path.exists(TARGET_PATH):
            try:
                os.remove(TARGET_PATH)
            except Exception:
                pass
        raise RuntimeError(f'Failed to download Noto Sans: {e}')


if __name__ == '__main__':
    download_noto()
