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
