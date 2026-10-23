from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

from screen_translate import snipaste_native as native


def test_icon_only_toolbar_and_copy_action(monkeypatch):
    def element(cls, rect, handle=0):
        return SimpleNamespace(CurrentName="Snipaste" if handle else "", CurrentClassName=cls,
            CurrentBoundingRectangle=rect, CurrentProcessId=12, CurrentNativeWindowHandle=handle,
            CurrentIsOffscreen=False, CurrentIsEnabled=True)
    pane = element("QWidget", (440, 541, 867, 574), 722706)
    row = [element("QPushButton", (441+i*32, 542, 473+i*32, 574)) for i in range(13)]
    row[-1].CurrentBoundingRectangle = (834, 542, 866, 574)
    root = SimpleNamespace(CurrentProcessId=12)
    automation = Mock()
    automation.ElementFromHandle.return_value = root
    module = SimpleNamespace(IUIAutomationInvokePattern=object())
    @contextmanager
    def session():
        yield automation, module
    def elements(parent, _automation, condition):
        if parent is pane:
            return iter(row)
        if condition is automation.CreateOrCondition.return_value:
            return iter([])
        if condition is automation.CreatePropertyCondition.return_value:
            return iter(row)
        return iter([pane])
    monkeypatch.setattr(native, "_uia_session", session)
    monkeypatch.setattr(native, "_elements", elements)
    monkeypatch.setattr(native.threading, "current_thread", lambda: object())
    monkeypatch.setattr(native, "_assert_trusted_snipper", lambda _handle: 12)
    row[-1].GetCurrentPattern = Mock(return_value=Mock())
    assert native.probe_toolbar(10).rect == (440, 541, 867, 574)
    native.request_copy(10)
    row[-1].GetCurrentPattern.return_value.QueryInterface.return_value.Invoke.assert_called_once()


def test_copy_uses_verified_toolbar_without_scanning_capture_tree(monkeypatch):
    pane = SimpleNamespace(CurrentName='Snipaste', CurrentClassName='QWidget',
        CurrentBoundingRectangle=(440, 541, 867, 574), CurrentProcessId=12,
        CurrentNativeWindowHandle=20)
    row = [SimpleNamespace(CurrentName='', CurrentClassName='QPushButton',
        CurrentBoundingRectangle=(441+i*32, 542, 473+i*32, 574), CurrentProcessId=12,
        CurrentNativeWindowHandle=0, CurrentIsOffscreen=False, CurrentIsEnabled=True)
        for i in range(13)]
    row[-1].CurrentBoundingRectangle = (834, 542, 866, 574)
    row[-1].GetCurrentPattern = Mock(return_value=Mock())
    root = SimpleNamespace(CurrentProcessId=12)
    automation = Mock()
    automation.ElementFromHandle.side_effect = lambda handle: root if handle == 10 else pane
    module = SimpleNamespace(IUIAutomationInvokePattern=object())
    @contextmanager
    def session():
        yield automation, module
    def elements(parent, *_args):
        assert parent is pane, 'Copy must use the known toolbar, not rescan Snipper'
        return iter(row)
    monkeypatch.setattr(native, '_uia_session', session)
    monkeypatch.setattr(native, '_elements', elements)
    monkeypatch.setattr(native.threading, 'current_thread', lambda: object())
    monkeypatch.setattr(native, '_assert_trusted_snipper', lambda _: 12)
    monkeypatch.setattr(native, '_window_data', lambda _: native.SnipWindow(
        20, 'Snipaste', 'Qt6QWindowIcon', (440, 541, 867, 574), 12))
    native.request_copy(10, 20)
    row[-1].GetCurrentPattern.return_value.QueryInterface.return_value.Invoke.assert_called_once()
