from PySide6.QtGui import QImage, QColor
import numpy as np
import pytest
from screen_translate.models import OcrResult, Rect, TextBlock
from screen_translate.image_translation import paragraphs, render
from screen_translate import image_translation


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


@pytest.mark.parametrize('format', [QImage.Format.Format_RGB32, QImage.Format.Format_ARGB32,
    QImage.Format.Format_RGB888, QImage.Format.Format_RGBA8888])
def test_vector_color_sampling_preserves_pixel_colors_stride_alpha_and_edge_clipping(format):
    pixels = np.random.default_rng(12).integers(0, 256, (61, 83, 4), dtype=np.uint8)
    image = QImage(pixels.data, 83, 61, pixels.strides[0], QImage.Format.Format_RGBA8888).convertToFormat(format)
    owner, view = image_translation._rgb_view(image)
    assert owner is not None
    for region in [image_translation.Region([block('one', 3.5, 4.2, 62, 30), block('two', 8, 40, 60, 15)]),
                   image_translation.Region([block('outside', -120, -110, 10, 10)]),
                   image_translation.Region([block('edge', 75, 52, 35, 30)])]:
        old = image_translation._colors(image, region)
        new = image_translation._colors(image, region, view)
        assert [c.getRgb() for c in old] == [c.getRgb() for c in new]


def test_vector_sampling_produces_identical_rendered_image(monkeypatch):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(['tests', '-platform', 'offscreen'])
    image = QImage(401, 160, QImage.Format.Format_ARGB32)
    image.fill(QColor('#f8f8fa'))
    for x in range(15, 290, 8):
        for y in range(20, 42):
            image.setPixelColor(x, y, QColor('#282d32'))
    regions = paragraphs(OcrResult([block('Hello world', 12, 16, 300, 30)], 'en', 401, 160))
    optimized = render(image, regions, ['你好，世界'])
    monkeypatch.setattr(image_translation, '_rgb_view', lambda _: (None, None))
    assert render(image, regions, ['你好，世界']) == optimized
