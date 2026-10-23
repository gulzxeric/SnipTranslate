"""Render a real OCR + Google result without opening a desktop window."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtGui import QFontDatabase, QImage
from PySide6.QtWidgets import QApplication
from screen_translate.common import image_bytes
from screen_translate.ocr import recognize_image
from screen_translate.google_translate import translate
from screen_translate.image_translation import paragraphs, render
from screen_translate.image_result import ImageResultWindow

app = QApplication([])
for font in ['msyh.ttc', 'segoeui.ttf']:
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
source = QImage(sys.argv[1])
assert not source.isNull()
ocr = recognize_image(image_bytes(source))
regions = paragraphs(ocr)
result = translate([region.text for region in regions])
for region, translated in zip(regions, result.texts):
    print(region.rect, repr(region.text), '->', translated)
output = render(source, regions, result.texts)
output.save('artifacts/translated-reference.png')
viewer = ImageResultWindow()
viewer.set_source(source)
viewer.set_result(output)
viewer.show()
app.processEvents()
viewer.grab().save('artifacts/image-result-preview.png')
viewer.close()
