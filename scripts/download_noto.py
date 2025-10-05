import os
import urllib.request

FONT_URL = 'https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf'
TARGET_DIR = os.path.join(os.getcwd(), 'fonts')
TARGET_PATH = os.path.join(TARGET_DIR, 'NotoSans-Regular.ttf')

os.makedirs(TARGET_DIR, exist_ok=True)
print('Downloading Noto Sans from', FONT_URL)
urllib.request.urlretrieve(FONT_URL, TARGET_PATH)
print('Saved to', TARGET_PATH)
