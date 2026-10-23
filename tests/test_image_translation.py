from PySide6.QtGui import QImage, QColor
from screen_translate.models import OcrResult, Rect, TextBlock
from screen_translate.image_translation import paragraphs, render


def block(text, x, y, width=300, height=20):
    return TextBlock(text, Rect(x, y, width, height))


def test_wrap_lines_join_but_headers_and_columns_stay_separate():
    ocr = OcrResult([block('Title', 20, 10, height=40), block('First line', 20, 80),
        block('continues here.', 20, 108), block('New paragraph.', 20, 170),
        block('Right column.', 450, 170)], 'en', 800, 250)
    regions = paragraphs(ocr)
    assert [r.text for r in regions] == ['Title', 'First line continues here.', 'New paragraph.', 'Right column.']


def test_hyphenated_wrapping_rejoins_word():
    ocr = OcrResult([block('No depen-', 10, 10), block('dencies.', 10, 36)], 'en', 400, 100)
    assert paragraphs(ocr)[0].text == 'No dependencies.'


def test_split_detections_on_same_line_are_translated_together():
    ocr = OcrResult([block('Hello world! Download', 10, 10, 280),
                    block('the document.', 300, 10, 180)], 'en', 600, 100)
    assert [r.text for r in paragraphs(ocr)] == ['Hello world! Download the document.']


def test_unchanged_translation_does_not_damage_original_pixels():
    image = QImage(400, 100, QImage.Format.Format_RGB32)
    image.fill(QColor('#284f67'))
    ocr = OcrResult([block('identifier', 10, 10)], 'en', 400, 100)
    assert render(image, paragraphs(ocr), ['identifier']) == image


def test_incomplete_translation_mapping_is_rejected():
    image = QImage(400, 100, QImage.Format.Format_RGB32)
    ocr = OcrResult([block('Hello', 10, 10)], 'en', 400, 100)
    import pytest
    with pytest.raises(ValueError):
        render(image, paragraphs(ocr), [])
