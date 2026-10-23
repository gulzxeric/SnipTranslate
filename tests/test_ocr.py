from types import SimpleNamespace

import pytest

from screen_translate.models import OcrResult, Rect, TextBlock
from screen_translate.ocr import OcrError, _line_rect, _scaled_dimensions, recognize


def word(x, y, width, height):
    return SimpleNamespace(bounding_rect=SimpleNamespace(x=x, y=y, width=width, height=height))


def test_line_bounds_union_words_and_scale_back_to_original_screenshot():
    # The second word is higher and taller, so using only the first word's y
    # or summing widths would position a translation incorrectly.
    rect = _line_rect([word(10, 12, 20, 8), word(35, 10, 15, 15)], 2.0, 3.0)
    assert rect == Rect(20.0, 30.0, 80.0, 45.0)


def test_empty_ocr_line_does_not_create_an_origin_rectangle():
    assert _line_rect([]) is None


@pytest.mark.parametrize("width,height,limit,expected", [
    (800, 600, 2600, (800, 600)),
    (5200, 2600, 2600, (2600, 1300)),
    (5200, 2601, 2600, (2600, 1300)),
    (1, 5200, 2600, (1, 2600)),
])
def test_scaled_image_respects_max_dimension_and_positive_size(width, height, limit, expected):
    assert _scaled_dimensions(width, height, limit) == expected


def test_result_text_uses_ocr_line_order():
    result = OcrResult([TextBlock("hello", Rect(0, 0, 10, 10)), TextBlock("world", Rect(0, 20, 10, 10))], "en-US", 100, 100)
    assert result.text == "hello\nworld"


def test_empty_image_has_useful_error_before_loading_windows_components():
    with pytest.raises(OcrError, match="截图为空"):
        recognize(b"")


def test_synchronous_api_passes_language_and_encoded_image_to_async_worker(monkeypatch):
    async def fake_recognize(image_bytes, language):
        assert image_bytes == b"encoded-png"
        assert language == "en-US"
        return OcrResult([], language, 2, 3)

    monkeypatch.setattr("screen_translate.ocr._recognize_async", fake_recognize)
    assert recognize(b"encoded-png", "en-US").height == 3
