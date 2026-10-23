"""Measure pipeline stages on an explicitly provided screenshot."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from time import perf_counter
from PySide6.QtGui import QImage, QFontDatabase
from PySide6.QtWidgets import QApplication
from screen_translate.common import image_bytes
from screen_translate.ocr import recognize_image
from screen_translate.google_translate import translate
from screen_translate.image_translation import paragraphs, render

app = QApplication([])
QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
source = QImage(sys.argv[1])
encoded = image_bytes(source)
for index in range(3):
    started = perf_counter()
    ocr = recognize_image(encoded)
    print(f'OCR {index}: {perf_counter()-started:.3f}s', flush=True)
regions = paragraphs(ocr)
started = perf_counter()
translated = translate([r.text for r in regions])
print(f'Google ({len(regions)} regions): {perf_counter()-started:.3f}s', flush=True)
started = perf_counter()
render(source, regions, translated.texts)
print(f'Render: {perf_counter()-started:.3f}s', flush=True)
