from io import BytesIO

from PIL import Image
from PySide6.QtGui import QColor, QImage
import pytest

from screen_translate.common import image_bytes


@pytest.mark.parametrize('format', [QImage.Format.Format_RGB32, QImage.Format.Format_ARGB32,
    QImage.Format.Format_RGBA8888])
def test_in_memory_bmp_and_png_have_identical_ocr_rgb_pixels(format):
    image = QImage(83, 61, format)
    image.fill(QColor(12, 34, 56, 70))
    image.setPixelColor(80, 55, QColor(210, 198, 175, 125))
    png = Image.open(BytesIO(image_bytes(image))).convert('RGB')
    bmp = Image.open(BytesIO(image_bytes(image, 'BMP'))).convert('RGB')
    assert png.size == bmp.size == (83, 61)
    assert png.tobytes() == bmp.tobytes()
