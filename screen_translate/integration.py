"""Launch the installed Snipaste through its documented command-line API."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
import os
import subprocess
import sys
from typing import Iterator


class IntegrationError(RuntimeError):
    """An integration failure that can be displayed directly to the user."""


def _executable(path: str) -> Path:
    if not isinstance(path, str) or not path.strip():
        raise IntegrationError("请先在设置中选择 Snipaste.exe。")
    try:
        executable = Path(os.path.expandvars(path.strip().strip('"'))).expanduser().resolve(strict=True)
    except (OSError, ValueError, RuntimeError):
        raise IntegrationError("找不到 Snipaste 程序，请在设置中重新选择 Snipaste.exe。") from None
    if not executable.is_file() or executable.suffix.lower() != ".exe":
        raise IntegrationError("Snipaste 路径无效，请选择 Snipaste.exe 文件。")
    return executable


def _process_images() -> Iterator[str]:
    if sys.platform != "win32":
        raise IntegrationError("Snipaste 联动仅支持 Windows。")

    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32FirstW.restype = wintypes.BOOL
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.restype = wintypes.BOOL
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    snapshot = kernel.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
    if snapshot == ctypes.c_void_p(-1).value:
        raise IntegrationError("无法读取 Windows 进程，请稍后重试。")
    entry = ProcessEntry()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        more = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            # Querying the full path avoids mistaking a different installation
            # for the executable selected by the user.
            process = kernel.OpenProcess(0x1000, False, entry.th32ProcessID)
            if process:
                try:
                    size = wintypes.DWORD(32768)
                    buffer = ctypes.create_unicode_buffer(size.value)
                    if kernel.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
                        yield buffer.value
                finally:
                    kernel.CloseHandle(process)
            more = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)


def is_snipaste_running(path: str) -> bool:
    """Check the full executable path, including when several copies exist."""
    executable = _executable(path)
    wanted = os.path.normcase(str(executable))
    processes = _process_images()
    try:
        return any(os.path.normcase(image) == wanted for image in processes)
    finally:
        # A short-circuited generator must still close the snapshot/handle.
        processes.close()


def _launch(executable: Path, *arguments: str) -> None:
    try:
        subprocess.Popen(
            [str(executable), *arguments], cwd=str(executable.parent),
            close_fds=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        raise IntegrationError("无法启动 Snipaste，请检查程序路径及访问权限。") from None


def start_snipaste(path: str) -> bool:
    """Start only if needed; return True when the caller should wait for startup."""
    executable = _executable(path)
    if is_snipaste_running(str(executable)):
        return False
    _launch(executable)
    return True


def snip_with_snipaste(path: str) -> None:
    """Ask an existing Snipaste instance to capture an image to the clipboard."""
    _launch(_executable(path), "snip", "-o", "clipboard")
