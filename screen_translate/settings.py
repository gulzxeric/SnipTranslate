"""Local preferences, with Windows DPAPI protecting the optional Cloud key."""
from __future__ import annotations

import base64
import ctypes
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from ctypes import wintypes


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(value: bytes, decrypt: bool = False) -> bytes:
    if os.name != "nt":
        raise RuntimeError("API Key 加密存储需要 Windows。")
    buffer = ctypes.create_string_buffer(value)
    incoming = _Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = _Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    function.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                         ctypes.POINTER(_Blob)]
    function.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not function(ctypes.byref(incoming), None, None, None, None, 1,
                    ctypes.byref(outgoing)):
        raise OSError("Windows 无法加密或解密 API Key。")
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        kernel32.LocalFree(outgoing.data)


def config_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "SnipTranslate" / "settings.json"


def default_snipaste_path() -> str:
    base = Path.home()
    candidates = [base / "Snipaste-2.11.3-x64" / "Snipaste.exe"]
    candidates += sorted(base.glob("Snipaste*/Snipaste.exe"), reverse=True)
    return str(next((p for p in candidates if p.is_file()), candidates[0]))


@dataclass
class Settings:
    ocr_engine: str = "rapidocr"
    target_language: str = "zh-CN"
    source_language: str = "auto"
    ocr_language: str = "auto"
    provider: str = "public"
    api_key: str = ""
    proxy: str = ""
    snipaste_path: str = ""
    auto_translate_clipboard: bool = False
    always_on_top: bool = False

    @classmethod
    def load(cls) -> "Settings":
        preferences = cls(snipaste_path=default_snipaste_path())
        try:
            data = json.loads(config_path().read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return preferences
            for name in cls.__dataclass_fields__:
                if name == "api_key" or name not in data:
                    continue
                if isinstance(data[name], type(getattr(preferences, name))):
                    setattr(preferences, name, data[name])
            if data.get("encrypted_api_key"):
                preferences.api_key = _crypt(base64.b64decode(data["encrypted_api_key"]), True).decode()
        except (OSError, ValueError, TypeError, RuntimeError):
            pass
        if preferences.provider not in {"public", "official"}:
            preferences.provider = "public"
        return preferences

    def save(self) -> None:
        data = asdict(self)
        key = data.pop("api_key")
        if key:
            data["encrypted_api_key"] = base64.b64encode(_crypt(key.encode())).decode("ascii")
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    @property
    def effective_api_key(self) -> str:
        return self.api_key or os.environ.get("GOOGLE_TRANSLATE_API_KEY", "")
