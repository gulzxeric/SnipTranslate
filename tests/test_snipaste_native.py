from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from screen_translate import snipaste_native as native


def element(name="", cls="", rect=(1, 2, 101, 42), pid=12, handle=0, offscreen=False, enabled=True):
    return SimpleNamespace(CurrentName=name, CurrentClassName=cls,
                           CurrentBoundingRectangle=SimpleNamespace(left=rect[0], top=rect[1], right=rect[2], bottom=rect[3]),
                           CurrentProcessId=pid, CurrentNativeWindowHandle=handle,
                           CurrentIsOffscreen=offscreen, CurrentIsEnabled=enabled)


def session(monkeypatch, elements):
    root = SimpleNamespace(CurrentProcessId=12)
    automation = Mock()
    automation.ElementFromHandle.return_value = root
    module = SimpleNamespace(IUIAutomationInvokePattern=object())
    @contextmanager
    def fake_session():
        yield automation, module
    monkeypatch.setattr(native, "_uia_session", fake_session)
    monkeypatch.setattr(native, "_elements", lambda *_args: iter(elements))
    return module


def test_toolbar_prefers_explicit_paintbar_and_ignores_other_process(monkeypatch):
    session(monkeypatch, [element(cls="OtherToolbar"), element(cls="PaintBar", rect=(10, 20, 410, 60)),
                         element(cls="PaintBar", pid=99)])
    result = native.probe_toolbar(100)
    assert result.class_name == "PaintBar"
    assert result.rect == (10, 20, 410, 60)


def test_hidden_toolbar_is_not_reported(monkeypatch):
    session(monkeypatch, [element(cls="PaintBar", offscreen=True)])
    assert native.probe_toolbar(100) is None


@pytest.mark.parametrize("name,expected", [("复制", True), ("Copy (Ctrl+C)", True),
    ("复制（Ctrl+C）", True), ("&Copy", True), ("Copy as File", False), ("复制为文件", False), ("Undo", False)])
def test_copy_names(name, expected):
    assert native._copy_button_name(name) is expected


def test_snapshot_trusts_only_returned_installation(monkeypatch, tmp_path):
    executable = tmp_path / "Snipaste.exe"
    executable.touch()
    window = native.SnipWindow(100, "Snipper - Snipaste", "Qt6QWindowIcon", (0, 0, 100, 100), 12)
    monkeypatch.setattr(native, "_collect_windows", lambda _path: [window])
    assert native.NativeSnipaste(str(executable)).snapshot() == [window]
    with native._trust_lock:
        assert native._trusted_windows[100] == (12, native._canonical_path(str(executable)))


def test_native_handle_reuse_is_rejected(monkeypatch):
    native._trusted_windows[123] = (12, native._canonical_path(r"C:\Snipaste\Snipaste.exe"))
    monkeypatch.setattr(native, "_window_data", lambda _handle: native.SnipWindow(123, "Snipper - Snipaste", "Qt", (0, 0, 1, 1), 99))
    with pytest.raises(native.NativeSnipasteError, match="已变化"):
        native._assert_trusted_snipper(123)


def test_copy_invokes_only_matching_button(monkeypatch):
    copy = element(name="复制 (Ctrl+C)")
    pattern = Mock()
    copy.GetCurrentPattern = Mock(return_value=pattern)
    module = session(monkeypatch, [element(name="撤销"), copy])
    monkeypatch.setattr(native.threading, "current_thread", lambda: object())
    verified = Mock(return_value=12)
    monkeypatch.setattr(native, "_assert_trusted_snipper", verified)
    native.request_copy(100)
    pattern.QueryInterface.assert_called_once_with(module.IUIAutomationInvokePattern)
    pattern.QueryInterface.return_value.Invoke.assert_called_once_with()
    assert verified.call_count == 2


def test_multiple_copy_buttons_do_not_invoke(monkeypatch):
    session(monkeypatch, [element(name="复制"), element(name="Copy")])
    monkeypatch.setattr(native.threading, "current_thread", lambda: object())
    monkeypatch.setattr(native, "_assert_trusted_snipper", lambda _handle: 12)
    with pytest.raises(native.NativeSnipasteError, match="唯一识别"):
        native.request_copy(100)


def test_main_thread_uia_is_rejected():
    with pytest.raises(native.NativeSnipasteError, match="后台线程"):
        with native._uia_session():
            pass


def test_full_path_comparison_supports_extended_prefix():
    assert native._canonical_path(r"\\?\C:\Snipaste\SNIPASTE.EXE") == native._canonical_path(r"c:\snipaste\Snipaste.exe")
