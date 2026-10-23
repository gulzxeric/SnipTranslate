"""Local Windows OCR. No screenshot pixels are sent to a remote service."""

import asyncio
import sys
from typing import Any

from .models import OcrResult, Rect, TextBlock


class OcrError(RuntimeError):
    """An OCR failure with a message suitable for the settings/result UI."""


def _load_winrt() -> tuple[Any, ...]:
    if sys.platform != "win32":
        raise OcrError("此工具使用 Windows 本地文字识别，需要 Windows 10 或 Windows 11。")
    try:
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import (
            BitmapAlphaMode, BitmapDecoder, BitmapPixelFormat, BitmapTransform,
            ColorManagementMode, ExifOrientationMode,
        )
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream
    except (ImportError, OSError):
        raise OcrError("缺少 Windows OCR 组件，请重新运行安装依赖脚本。") from None
    return (
        Language, BitmapAlphaMode, BitmapDecoder, BitmapPixelFormat, BitmapTransform,
        ColorManagementMode, ExifOrientationMode, OcrEngine, DataWriter, InMemoryRandomAccessStream,
    )


def available_languages() -> list[tuple[str, str]]:
    """Return the OCR language packs that are actually installed in Windows."""
    *_, engine, _writer, _stream = _load_winrt()
    try:
        return [(item.language_tag, item.display_name) for item in engine.available_recognizer_languages]
    except Exception:
        raise OcrError("无法读取 Windows 识别语言，请在系统“语言和区域”中安装所需语言的 OCR 组件。") from None


def _line_rect(words: Any, scale_x: float = 1.0, scale_y: float = 1.0) -> Rect | None:
    """Union all word bounds and restore original image pixel coordinates."""
    bounds = [word.bounding_rect for word in words]
    if not bounds:
        return None
    left = min(rect.x for rect in bounds)
    top = min(rect.y for rect in bounds)
    right = max(rect.x + rect.width for rect in bounds)
    bottom = max(rect.y + rect.height for rect in bounds)
    return Rect(left * scale_x, top * scale_y, (right - left) * scale_x, (bottom - top) * scale_y)


def _scaled_dimensions(width: int, height: int, limit: int) -> tuple[int, int]:
    factor = min(1.0, limit / max(width, height))
    return max(1, int(width * factor)), max(1, int(height * factor))


async def _recognize_async(image_bytes: bytes, language: str) -> OcrResult:
    (
        Language, BitmapAlphaMode, BitmapDecoder, BitmapPixelFormat, BitmapTransform,
        ColorManagementMode, ExifOrientationMode, OcrEngine, DataWriter, InMemoryRandomAccessStream,
    ) = _load_winrt()
    if language == "auto":
        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            installed = list(OcrEngine.available_recognizer_languages)
            engine = OcrEngine.try_create_from_language(installed[0]) if installed else None
    else:
        try:
            engine = OcrEngine.try_create_from_language(Language(language))
        except Exception:
            raise OcrError("无法使用所选识别语言，请在设置中选择已安装的 OCR 语言。") from None
    if engine is None:
        raise OcrError("尚未安装所需 OCR 语言包，请打开 Windows 设置 → 时间和语言 → 语言和区域，安装该语言的文字识别组件。")

    stream = InMemoryRandomAccessStream()
    writer = None
    bitmap = None
    try:
        writer = DataWriter(stream)
        writer.write_bytes(image_bytes)
        await writer.store_async()
        writer.detach_stream()
        writer.close()
        writer = None
        stream.seek(0)
        decoder = await BitmapDecoder.create_async(stream)
        width, height = decoder.pixel_width, decoder.pixel_height
        if width < 1 or height < 1:
            raise OcrError("截图尺寸无效，请重新截图。")
        scaled_width, scaled_height = _scaled_dimensions(width, height, OcrEngine.max_image_dimension)
        transform = BitmapTransform()
        transform.scaled_width = scaled_width
        transform.scaled_height = scaled_height
        bitmap = await decoder.get_software_bitmap_transformed_async(
            BitmapPixelFormat.BGRA8, BitmapAlphaMode.PREMULTIPLIED, transform,
            ExifOrientationMode.IGNORE_EXIF_ORIENTATION, ColorManagementMode.DO_NOT_COLOR_MANAGE,
        )
        raw = await engine.recognize_async(bitmap)
        blocks = []
        for line in raw.lines:
            rect = _line_rect(line.words, width / scaled_width, height / scaled_height)
            if rect is not None and line.text.strip():
                blocks.append(TextBlock(line.text, rect))
        return OcrResult(blocks, engine.recognizer_language.language_tag, width, height)
    finally:
        if writer is not None:
            writer.close()
        if bitmap is not None:
            bitmap.close()
        stream.close()


def recognize(image_bytes: bytes, language: str = "auto") -> OcrResult:
    """Recognize one encoded screenshot synchronously in a background worker.

    ``auto`` selects an installed recognizer from the Windows user profile; the
    Windows OCR API itself does not provide automatic language detection.
    """
    if not isinstance(image_bytes, bytes) or not image_bytes:
        raise OcrError("截图为空，请重新选择截图区域。")
    try:
        return asyncio.run(_recognize_async(image_bytes, language))
    except OcrError:
        raise
    except Exception:
        raise OcrError("Windows 文字识别失败。请确认截图有效，并在系统设置中安装所选语言的 OCR 组件。") from None
