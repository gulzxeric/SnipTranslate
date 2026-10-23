import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication
from screen_translate.image_result import ImageResultWindow
from screen_translate.image_translation import paragraphs, render
from screen_translate.models import OcrResult, TextBlock, Rect


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance() or QApplication(['tests', '-platform', 'offscreen'])
    yield app


def test_switch_and_copy_preserve_original_and_translated_pixels(qapp):
    source = QImage(600, 240, QImage.Format.Format_RGB32)
    source.fill(QColor('white'))
    translated = source.copy()
    translated.fill(QColor('#e6f8ef'))
    window = ImageResultWindow()
    window.set_source(source)
    window.set_result(translated)
    assert window.current_image() == translated
    window.toggle.setChecked(False)
    assert window.current_image() == source
    window.copy_image()
    assert QApplication.clipboard().image() == source
    window.close()


def test_closing_loading_preview_does_not_reopen_after_completion(qapp):
    image = QImage(600, 240, QImage.Format.Format_RGB32)
    image.fill(QColor('white'))
    window = ImageResultWindow()
    window.set_source(image)
    window.show_busy()
    assert window.isVisible()
    window.close()
    window.set_result(image)
    assert not window.isVisible()
    assert not window._backdrops


def test_render_does_not_change_unrelated_image_regions(qapp):
    source = QImage(600, 240, QImage.Format.Format_RGB32)
    source.fill(QColor('white'))
    source.setPixelColor(500, 210, QColor('#123456'))
    ocr = OcrResult([TextBlock('Hello', Rect(10, 10, 150, 24))], 'en', 600, 240)
    translated = render(source, paragraphs(ocr), ['你好'])
    assert source.pixelColor(500, 210) == translated.pixelColor(500, 210)
    assert source != translated
