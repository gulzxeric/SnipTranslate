from time import perf_counter
from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtCore import QObject
from PySide6.QtGui import QImage

from screen_translate import companion


def test_clipboard_starts_translation_before_invoke_returns(monkeypatch):
    owner = companion.Companion.__new__(companion.Companion)
    QObject.__init__(owner)
    owner._snipper = SimpleNamespace(handle=10)
    owner._toolbar = SimpleNamespace(handle=20)
    owner._busy = owner._waiting = False
    owner._copy_request = 0
    owner.preferences = SimpleNamespace(snipaste_path='Snipaste.exe')
    owner.button = Mock()
    owner.clipboard_timer = Mock()
    owner.copy_timeout = Mock()
    owner.result = Mock()
    owner.image_result = Mock()
    owner.start_translation = Mock()
    callbacks = []
    def submit(callback, success, failure):
        owner.clipboard_timer.start.assert_called_once()
        owner.copy_timeout.start.assert_called_once()
        callbacks.extend([success, failure])
        # Leave the copy invocation pending while its clipboard event arrives.
    owner._task = submit
    monkeypatch.setattr(companion, 'clipboard_sequence', lambda: 11)
    monkeypatch.setattr('screen_translate.capture_location.begin_capture_log', lambda _: None)
    monkeypatch.setattr('screen_translate.capture_location.capture_rectangle', lambda *_: None)
    image = QImage(10, 10, QImage.Format.Format_RGB32)
    image.fill(0xffffffff)
    monkeypatch.setattr(companion, 'QApplication', SimpleNamespace(
        clipboard=lambda: SimpleNamespace(image=lambda: image)))
    owner.copy_selected_image()
    monkeypatch.setattr(companion, 'clipboard_sequence', lambda: 12)
    owner.check_clipboard()
    owner.start_translation.assert_called_once()
    assert not owner._waiting
    assert owner._copy_elapsed >= 0
    owner.clipboard_timer.reset_mock()
    owner.copy_timeout.reset_mock()
    callbacks[0](None)
    callbacks[1]('Invoke returned late')
    owner.clipboard_timer.start.assert_not_called()
    owner.copy_timeout.start.assert_not_called()
    owner.result.set_error.assert_not_called()
    # A previous invocation must also leave a newer capture untouched.
    owner._waiting = True
    owner._copy_request += 1
    callbacks[1]('Old capture failed')
    assert owner._waiting
    owner.result.set_error.assert_not_called()


def test_retry_resets_click_time_without_recopying():
    owner = companion.Companion.__new__(companion.Companion)
    QObject.__init__(owner)
    owner._busy = False
    owner._request_started = 0
    owner._copy_elapsed = 3
    owner.start_translation = Mock()
    before = perf_counter()
    owner.retry()
    assert owner._request_started >= before
    assert owner._copy_elapsed == 0
    owner.start_translation.assert_called_once()
