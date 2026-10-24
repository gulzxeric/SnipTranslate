"""Native Snipaste discovery and accessibility integration.

Window enumeration and toolbar probes are read-only. ``request_copy`` is the
only action: it invokes Snipaste's own Copy button, and only on a window that
was previously verified against the configured executable by ``snapshot``.
All UI Automation operations must be called from one dedicated worker thread.
No synthetic keyboard/mouse input, window changes, or process injection is used.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import ctypes
from ctypes import wintypes
from functools import lru_cache
import json
import ntpath
import sys
import threading
from typing import Any, Iterator

from .integration import IntegrationError, _executable
from .cancellation import CancelledError, check_cancelled


class NativeSnipasteError(IntegrationError):
    """An actionable native integration error."""


@dataclass(frozen=True, slots=True)
class SnipWindow:
    handle: int
    title: str
    class_name: str
    rect: tuple[int, int, int, int]
    process_id: int


_trusted_windows: dict[int, tuple[int, str]] = {}
_trust_lock = threading.Lock()


def _canonical_path(path: str) -> str:
    # QueryFullProcessImageName normally returns a DOS path. Account for an
    # extended-length prefix without broadening matching to the basename.
    if path.startswith("\\\\?\\"):
        path = path[4:]
    return ntpath.normcase(ntpath.normpath(path))


@lru_cache(maxsize=1)
def _win32():
    if sys.platform != "win32":
        raise NativeSnipasteError("Snipaste 原生工具栏联动仅支持 Windows。")
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback, wintypes.LPARAM]
    user.EnumWindows.restype = wintypes.BOOL
    user.EnumChildWindows.argtypes = [wintypes.HWND, callback, wintypes.LPARAM]
    user.EnumChildWindows.restype = wintypes.BOOL
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.IsWindowVisible.restype = wintypes.BOOL
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowThreadProcessId.restype = wintypes.DWORD
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.GetWindowRect.restype = wintypes.BOOL
    user.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user.GetWindowTextLengthW.restype = ctypes.c_int
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindowTextW.restype = ctypes.c_int
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetClassNameW.restype = ctypes.c_int
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    return user, kernel, callback


def _process_image(process_id: int) -> str:
    _user, kernel, _callback = _win32()
    process = kernel.OpenProcess(0x1000, False, process_id)
    if not process:
        return ""
    try:
        length = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(length.value)
        if kernel.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(length)):
            return buffer.value
        return ""
    finally:
        kernel.CloseHandle(process)


def _window_pid(handle: int) -> int:
    user, _kernel, _callback = _win32()
    process_id = wintypes.DWORD()
    user.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
    return process_id.value


def _window_data(handle: int) -> SnipWindow | None:
    user, _kernel, _callback = _win32()
    if not user.IsWindowVisible(handle):
        return None
    rect = wintypes.RECT()
    if not user.GetWindowRect(handle, ctypes.byref(rect)):
        return None
    title = ctypes.create_unicode_buffer(max(1, user.GetWindowTextLengthW(handle) + 1))
    user.GetWindowTextW(handle, title, len(title))
    class_name = ctypes.create_unicode_buffer(512)
    user.GetClassNameW(handle, class_name, len(class_name))
    return SnipWindow(int(handle), title.value, class_name.value,
                      (rect.left, rect.top, rect.right, rect.bottom), _window_pid(handle))


def _collect_windows(executable: str) -> list[SnipWindow]:
    user, _kernel, callback_type = _win32()
    images: dict[int, str] = {}
    collected: dict[int, SnipWindow] = {}
    failure: list[Exception] = []

    def matches(pid: int) -> bool:
        if pid not in images:
            images[pid] = _canonical_path(_process_image(pid)) if pid else ""
        return images[pid] == executable

    def collect(handle, _parameter):
        try:
            pid = _window_pid(handle)
            if matches(pid):
                data = _window_data(handle)
                if data:
                    collected[data.handle] = data
        except Exception as exc:
            failure.append(exc)
        return True

    child_callback = callback_type(collect)

    def visit_top(handle, parameter):
        collect(handle, parameter)
        # EnumChildWindows recursively enumerates all descendants, including
        # descendants whose immediate parent has no useful window text.
        if matches(_window_pid(handle)):
            user.EnumChildWindows(handle, child_callback, 0)
        return True

    top_callback = callback_type(visit_top)
    if not user.EnumWindows(top_callback, 0):
        raise NativeSnipasteError("无法枚举 Snipaste 窗口，请稍后重试。")
    if failure and not collected:
        raise NativeSnipasteError("无法读取 Snipaste 窗口信息，请检查程序权限。")
    return list(collected.values())


class NativeSnipaste:
    def __init__(self, path: str):
        self.executable = str(_executable(path))
        self._identity = _canonical_path(self.executable)

    def snapshot(self) -> list[SnipWindow]:
        """Visible top-level and descendant HWNDs belonging to this exact EXE.

        Rectangles are physical screen coordinates, so the caller should use
        per-monitor DPI awareness and convert for Qt's logical coordinates.
        Qt alien widgets do not appear here; use ``probe_toolbar`` for those.
        """
        windows = _collect_windows(self._identity)
        with _trust_lock:
            # Remove this installation's stale HWNDs, which may later be reused.
            for handle, (_pid, image) in list(_trusted_windows.items()):
                if image == self._identity:
                    del _trusted_windows[handle]
            _trusted_windows.update({item.handle: (item.process_id, self._identity) for item in windows})
        return windows


@contextmanager
def _uia_session() -> Iterator[tuple[Any, Any]]:
    if threading.current_thread() is threading.main_thread():
        raise NativeSnipasteError("工具栏识别必须在专用后台线程中运行。")
    if sys.platform != "win32":
        raise NativeSnipasteError("工具栏识别仅支持 Windows。")
    try:
        import comtypes
        import comtypes.client
    except ImportError:
        raise NativeSnipasteError("缺少工具栏识别依赖，请安装 comtypes 后重试。") from None
    initialized = False
    automation = None
    try:
        # comtypes initializes the importing thread once. Every worker call also
        # owns a balanced initialization so subsequent calls/threads are valid.
        comtypes.CoInitializeEx()
        initialized = True
        module = comtypes.client.GetModule("UIAutomationCore.dll")
        automation = comtypes.client.CreateObject(module.CUIAutomation, interface=module.IUIAutomation)
        yield automation, module
    except (NativeSnipasteError, CancelledError):
        raise
    except Exception as exc:
        raise NativeSnipasteError("无法读取 Snipaste 无障碍控件，请确认截图窗口仍打开且程序权限一致。") from exc
    finally:
        automation = None
        if initialized:
            comtypes.CoUninitialize()


def _rect(value: Any) -> tuple[int, int, int, int]:
    if all(hasattr(value, name) for name in ("left", "top", "right", "bottom")):
        return tuple(int(getattr(value, name)) for name in ("left", "top", "right", "bottom"))
    return tuple(int(number) for number in value)


def _element_data(element: Any) -> SnipWindow:
    return SnipWindow(int(element.CurrentNativeWindowHandle or 0), str(element.CurrentName or ""),
                      str(element.CurrentClassName or ""), _rect(element.CurrentBoundingRectangle),
                      int(element.CurrentProcessId))


def _visible(data: SnipWindow, element: Any) -> bool:
    left, top, right, bottom = data.rect
    return not bool(element.CurrentIsOffscreen) and right > left and bottom > top


def _elements(root: Any, automation: Any, condition: Any) -> Iterator[Any]:
    found = root.FindAll(4, condition)  # TreeScope_Descendants
    for index in range(found.Length):
        yield found.GetElement(index)


def probe_toolbar(snipper_handle: int) -> SnipWindow | None:
    """Read a PaintBar/ToolBar rectangle in a dedicated UIA worker thread.

    None means a successful query found no visible matching element. A custom
    Qt PaintBar may expose neither its class nor ToolBar role; diagnostics can
    inspect its child buttons without claiming a stable toolbar exists.
    """
    with _uia_session() as (automation, _module):
        root = automation.ElementFromHandle(snipper_handle)
        pid = int(root.CurrentProcessId)
        condition = automation.CreateOrCondition(
            automation.CreatePropertyCondition(30003, 50021),  # ControlType.ToolBar
            automation.CreatePropertyCondition(30012, "PaintBar"),  # ClassName
        )
        candidates = []
        for element in _elements(root, automation, condition):
            data = _element_data(element)
            if data.process_id == pid and _visible(data, element):
                candidates.append(data)
        candidates.sort(key=lambda item: item.class_name != "PaintBar")
        if candidates:
            return candidates[0]
        # Snipaste 2.11.3 exposes its toolbar as an owned QWidget pane rather
        # than a ToolBar role. Verify the actual row of icon buttons within it.
        for element in _elements(root, automation, automation.CreateTrueCondition()):
            data = _element_data(element)
            l, t, r, b = data.rect
            if (data.process_id == pid and data.handle and data.class_name == "QWidget"
                    and data.title == "Snipaste" and 24 <= b-t <= 120 and r-l >= 250
                    and (r-l) > 5*(b-t) and _visible(data, element)):
                controls = list(_elements(element, automation, automation.CreateTrueCondition()))
                buttons = [e for e in controls if str(e.CurrentClassName) == "QPushButton"]
                if len(buttons) >= 8:
                    return data
        return None


def inspect_accessibility(snipper_handle: int, limit: int = 300) -> list[dict[str, Any]]:
    """Read diagnostic descendants; no actions or pattern invocation occurs."""
    with _uia_session() as (automation, _module):
        root = automation.ElementFromHandle(snipper_handle)
        rows = []
        for element in _elements(root, automation, automation.CreateTrueCondition()):
            data = _element_data(element)
            rows.append({**asdict(data), "control_type": int(element.CurrentControlType),
                         "offscreen": bool(element.CurrentIsOffscreen),
                         "enabled": bool(element.CurrentIsEnabled)})
            if len(rows) >= max(1, min(limit, 2000)):
                break
        return rows


def _assert_trusted_snipper(handle: int) -> int:
    with _trust_lock:
        identity = _trusted_windows.get(handle)
    if identity is None:
        raise NativeSnipasteError("截图窗口尚未验证，请重新开始截图后重试。")
    pid, image = identity
    live = _window_data(handle)
    if (live is None or live.process_id != pid or _canonical_path(_process_image(pid)) != image
            or "snipper" not in live.title.casefold() or "snipaste" not in live.title.casefold()):
        raise NativeSnipasteError("Snipaste 截图窗口已变化，请重新截图后重试。")
    return pid


def _copy_button_name(name: str) -> bool:
    value = name.strip().replace("&", "").casefold()
    # Accept shortcut suffixes such as Copy (Ctrl+C), but avoid Copy as File.
    for prefix in ("复制", "copy"):
        if value == prefix:
            return True
        if value.startswith(prefix):
            tail = value[len(prefix):].lstrip()
            if tail.startswith(("(", "（", "[", "\t")) or (tail and tail.casefold().startswith("ctrl")):
                return True
    return False


def _icon_copy_buttons(pane, automation, process_id):
    data = _element_data(pane)
    l, t, r, b = data.rect
    if not (data.process_id == process_id and data.handle and data.title == "Snipaste"
            and data.class_name == "QWidget" and 24 <= b-t <= 120 and r-l > 5*(b-t)):
        return []
    row = []
    for control in _elements(pane, automation, automation.CreateTrueCondition()):
        # Most descendants are not buttons. Avoid reading all their remote
        # properties across the UIA process boundary.
        if str(control.CurrentClassName) != "QPushButton":
            continue
        item = _element_data(control)
        if item.process_id == process_id and _visible(item, control):
            row.append((item, control))
    if len(row) >= 8:
        item, control = max(row, key=lambda pair: pair[0].rect[2])
        if (0 <= r-item.rect[2] <= 4 and abs(item.rect[1]-t) <= 4
                and bool(control.CurrentIsEnabled)):
            return [control]
    return []


def request_copy(snipper_handle: int, toolbar_handle: int = 0, *, cancel_event=None, before_invoke=None) -> None:
    """Invoke only the original verified Snipper's enabled Copy button.

    This must run on the same dedicated UIA worker used for probes. The caller
    subscribes to clipboard changes before requesting this action. No keyboard
    shortcut fallback is attempted when the accessible button is unavailable.
    """
    if threading.current_thread() is threading.main_thread():
        raise NativeSnipasteError("复制操作必须在专用后台线程中运行。")
    check_cancelled(cancel_event)
    process_id = _assert_trusted_snipper(snipper_handle)
    with _uia_session() as (automation, module):
        root = automation.ElementFromHandle(snipper_handle)
        if int(root.CurrentProcessId) != process_id:
            raise NativeSnipasteError("Snipaste 截图窗口已失效，请重新截图。")
        matches = []
        if toolbar_handle:
            live = _window_data(toolbar_handle)
            # The native HWND class is Qt...QWindowIcon; UIA reports QWidget.
            # Validate that UIA structure separately in _icon_copy_buttons.
            if live and live.process_id == process_id and live.title == 'Snipaste':
                pane = automation.ElementFromHandle(toolbar_handle)
                matches = _icon_copy_buttons(pane, automation, process_id)
        if not matches:
            buttons = automation.CreatePropertyCondition(30003, 50000)  # Button
            for element in _elements(root, automation, buttons):
                data = _element_data(element)
                if (data.process_id == process_id and _copy_button_name(data.title)
                        and _visible(data, element) and bool(element.CurrentIsEnabled)):
                    matches.append(element)
        if not matches:
            # This build's icon-only QPushButtons have empty accessible names.
            # Its original Copy action is the rightmost button, immediately
            # against the verified toolbar's right edge (Save is before it).
            for pane in _elements(root, automation, automation.CreateTrueCondition()):
                matches.extend(_icon_copy_buttons(pane, automation, process_id))
        if len(matches) != 1:
            raise NativeSnipasteError("无法唯一识别 Snipaste 的复制按钮，请使用原工具栏复制截图。")
        # Recheck the native identity immediately before the sole write action.
        _assert_trusted_snipper(snipper_handle)
        pattern = matches[0].GetCurrentPattern(10000)  # InvokePattern
        if not pattern:
            raise NativeSnipasteError("Snipaste 复制按钮不支持无障碍调用，请手动复制截图。")
        check_cancelled(cancel_event)
        if before_invoke is not None:
            before_invoke(ctypes.windll.user32.GetClipboardSequenceNumber())
        check_cancelled(cancel_event)
        pattern.QueryInterface(module.IUIAutomationInvokePattern).Invoke()


def _diagnose(path: str, accessibility: bool) -> None:
    native = NativeSnipaste(path)
    windows = native.snapshot()
    output: dict[str, Any] = {"executable": native.executable, "windows": [asdict(item) for item in windows]}
    if accessibility:
        from concurrent.futures import ThreadPoolExecutor
        output["accessibility"] = {}
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="snipaste-uia-diagnostics") as worker:
            for item in windows:
                if "snipper" in item.title.casefold():
                    try:
                        rows = worker.submit(inspect_accessibility, item.handle).result()
                        output["accessibility"][str(item.handle)] = rows
                    except NativeSnipasteError as exc:
                        output["accessibility"][str(item.handle)] = {"error": str(exc)}
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read-only Snipaste window diagnostics")
    parser.add_argument("--diagnose", action="store_true", required=True)
    parser.add_argument("--path", help="Full path to Snipaste.exe; defaults to saved settings")
    parser.add_argument("--accessibility", action="store_true", help="Also read the Snipper's accessibility tree")
    args = parser.parse_args()
    if not args.path:
        from .settings import Settings
        args.path = Settings.load().snipaste_path
    _diagnose(args.path, args.accessibility)
