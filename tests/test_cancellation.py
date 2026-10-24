from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Event
from time import perf_counter
from unittest.mock import Mock

from PIL import Image
import pytest
from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from screen_translate import companion
from screen_translate.image_result import ImageResultWindow
from screen_translate.models import OcrResult, Rect, TextBlock, TranslationResult
from screen_translate.settings import Settings
from screen_translate.snipaste_native import SnipWindow


@pytest.fixture
def owner():
    app = QApplication.instance() or QApplication(['tests', '-platform', 'offscreen'])
    controller = companion.Companion.__new__(companion.Companion)
    QObject.__init__(controller)
    controller.app = app
    controller.preferences = Settings()
    controller.workers = ThreadPoolExecutor(max_workers=2)
    controller._pipeline_jobs = {}
    controller._job_generation = controller._copy_request = 0
    controller._busy = controller._waiting = False
    controller._translation_cancel = controller._copy_cancel = None
    controller._copy_elapsed = 0
    controller._ocr = None
    controller._translated_text = ''
    controller.button = Mock()
    controller.clipboard_timer = Mock()
    controller.copy_timeout = Mock()
    controller.poll = Mock()
    controller.image_result = ImageResultWindow()
    controller.image_result.cancelled.connect(lambda: controller.cancel_translation(close_result=False))
    controller.translator = Mock()
    controller.translator.translate.side_effect = lambda texts, **_: TranslationResult([f'译文:{text}' for text in texts])
    yield controller
    controller.cancel_translation(refresh=False)
    controller.image_result.close()
    controller.workers.shutdown(wait=True, cancel_futures=True)
    app.processEvents()


def start(owner, marker):
    image = QImage(220, 100, QImage.Format.Format_RGB32)
    image.fill(QColor(marker, 240, 240))
    owner._image = image
    owner._ocr = None
    owner._request_started = perf_counter()
    owner.image_result.set_source(image)
    owner.start_translation()


def drain_until(owner, predicate):
    deadline = perf_counter() + 3
    while not predicate() and perf_counter() < deadline:
        owner.app.processEvents()
        QTest.qWait(5)
    assert predicate()


def recognized(data):
    marker = Image.open(BytesIO(data)).convert('RGB').getpixel((0, 0))[0]
    return OcrResult([TextBlock(str(marker), Rect(10, 10, 180, 22))], 'en', 220, 100)


def test_escape_releases_capture_and_old_ocr_cannot_start_network_or_replace_new_result(owner, monkeypatch):
    entered, release = Event(), Event()
    def ocr(data, *_args, **_kwargs):
        result = recognized(data)
        if result.text == '10':
            entered.set()
            assert release.wait(3)
        return result
    monkeypatch.setattr(companion, 'recognize_image', ocr)
    try:
        start(owner, 10)
        assert entered.wait(2)
        # Escape uses the same close path as the toolbar's Cancel button.
        QTest.keyClick(owner.image_result, Qt.Key.Key_Escape)
        owner.app.processEvents()
        assert not owner._busy and not owner._waiting
        assert not owner.image_result.isVisible()
        start(owner, 20)
        drain_until(owner, lambda: not owner._busy)
        assert owner._translated_text == '译文:20'
        release.set()
        owner.workers.shutdown(wait=True)
        owner.app.processEvents()
        assert owner._translated_text == '译文:20'
        assert owner.translator.translate.call_count == 1
    finally:
        release.set()


def test_already_queued_old_success_failure_and_progress_are_ignored(owner, monkeypatch):
    monkeypatch.setattr(companion, 'recognize_image', lambda data, *_args, **_kwargs: recognized(data))
    start(owner, 30)
    generation = owner._job_generation
    owner._pipeline_jobs[generation][1].result(timeout=2)
    owner.cancel_translation()
    start(owner, 40)
    owner.translation_failed('old error', generation)
    owner.translation_progress('old progress', generation)
    assert owner._busy
    drain_until(owner, lambda: not owner._busy)
    assert owner._translated_text == '译文:40'
    assert 'old' not in owner.image_result._message


def test_new_snipaste_capture_replaces_running_job_without_stealing_new_selection(owner, monkeypatch):
    entered, release = Event(), Event()
    def ocr(data, *_args, **_kwargs):
        entered.set()
        assert release.wait(3)
        return recognized(data)
    monkeypatch.setattr(companion, 'recognize_image', ocr)
    try:
        start(owner, 50)
        assert entered.wait(2)
        token = owner._translation_cancel
        owner._probing = False
        owner._toolbar = None
        owner._toolbar_snipper = owner._toolbar_misses = 0
        owner.state_action = Mock()
        snipper = SnipWindow(11, 'Snipper - Snipaste', 'Qt', (0,0,800,600), 12)
        toolbar = SnipWindow(22, 'Snipaste', 'QWidget', (100,500,700,540), 12)
        owner.probed((snipper, toolbar), supersede=True)
        assert not owner._busy and token.is_set()
        assert owner._snipper == snipper
        owner.button.set_anchor.assert_called_once_with(toolbar.rect)
        assert not owner.image_result.isVisible()
    finally:
        release.set()
