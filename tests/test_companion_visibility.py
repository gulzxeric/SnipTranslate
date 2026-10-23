from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtCore import QObject

from screen_translate.companion import Companion
from screen_translate.snipaste_native import SnipWindow


def controller():
    owner = Companion.__new__(Companion)
    QObject.__init__(owner)
    owner.button = Mock()
    owner.state_action = Mock()
    owner._busy = owner._waiting = False
    owner._toolbar = None
    owner._toolbar_snipper = owner._toolbar_misses = 0
    return owner


def test_transient_toolbar_miss_keeps_button_until_capture_ends():
    owner = controller()
    snipper = SnipWindow(1, 'Snipper - Snipaste', 'Qt', (0, 0, 1000, 800), 12)
    toolbar = SnipWindow(2, 'Snipaste', 'Qt', (10, 600, 600, 650), 12)
    owner.probed((snipper, toolbar))
    owner.button.reset_mock()
    owner.probed((snipper, None))
    owner.button.hide.assert_not_called()
    owner.probed((None, None))
    owner.button.hide.assert_called_once()


def test_inflight_probe_does_not_hide_button():
    owner = controller()
    owner._probing = True
    owner.poll()
    owner.button.hide.assert_not_called()


def test_hovering_other_tools_can_hide_toolbar_for_more_than_one_second():
    owner = controller()
    snipper = SnipWindow(1, 'Snipper - Snipaste', 'Qt', (0, 0, 1000, 800), 12)
    toolbar = SnipWindow(2, 'Snipaste', 'Qt', (10, 600, 600, 650), 12)
    owner.probed((snipper, toolbar))
    owner.button.reset_mock()
    for _ in range(30):
        owner.probed((snipper, None))
    owner.button.hide.assert_not_called()
    assert owner._toolbar == toolbar
    assert owner.button.keep_above.call_count == 30
    owner.probed((None, None))
    owner.button.hide.assert_called_once()


def test_old_button_does_not_follow_a_different_capture_window():
    owner = controller()
    old = SnipWindow(1, 'Snipper - Snipaste', 'Qt', (0, 0, 1000, 800), 12)
    new = SnipWindow(3, 'Snipper - Snipaste', 'Qt', (0, 0, 1000, 800), 12)
    toolbar = SnipWindow(2, 'Snipaste', 'Qt', (10, 600, 600, 650), 12)
    owner.probed((old, toolbar))
    owner.button.reset_mock()
    owner.probed((new, None))
    owner.button.hide.assert_called_once()


def test_accessibility_errors_during_hover_do_not_discard_confirmed_selection():
    owner = controller()
    snipper = SnipWindow(1, 'Snipper - Snipaste', 'Qt', (0, 0, 1000, 800), 12)
    toolbar = SnipWindow(2, 'Snipaste', 'Qt', (10, 600, 600, 650), 12)
    owner.probed((snipper, toolbar))
    owner.button.reset_mock()
    for _ in range(6):
        owner.probe_failed('native toolbar changing')
    owner.button.hide.assert_not_called()


def test_verified_toolbar_is_followed_without_repeating_accessibility(monkeypatch):
    owner = controller()
    snipper = SnipWindow(1, 'Snipper - Snipaste', 'Qt', (0, 0, 1000, 800), 12)
    toolbar = SnipWindow(2, 'Snipaste', 'Qt', (10, 600, 600, 650), 12)
    owner._toolbar, owner._toolbar_snipper = toolbar, 1
    owner.native = SimpleNamespace(snapshot=lambda: [snipper, toolbar])
    owner._probing = False
    owner._task = lambda callback, success, failure: success(callback())
    probe = Mock(side_effect=AssertionError('verified native toolbar must not require UIA again'))
    monkeypatch.setattr('screen_translate.snipaste_native.probe_toolbar', probe)
    owner.poll()
    owner.button.set_anchor.assert_called_once_with(toolbar.rect)
    probe.assert_not_called()
