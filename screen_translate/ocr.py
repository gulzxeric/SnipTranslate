"""Local Windows OCR. No screenshot pixels are sent to a remote service."""

import asyncio
import sys
import threading
from typing import Any

from .models import OcrResult, Rect, TextBlock

_rapid_engine = None
_rapid_lock = threading.Lock()


def recognize_image(image_bytes: bytes, language: str = 'auto', engine: str = 'rapidocr') -> OcrResult:
    if engine == 'windows':
        return recognize(image_bytes, language)
    if engine != 'rapidocr':
        raise OcrError('未知的文字识别引擎，请检查设置。')
    if not image_bytes:
        raise OcrError('截图为空，请重新截图。')
    global _rapid_engine
    try:
        from io import BytesIO
        from PIL import Image
        import numpy as np
        from rapidocr import RapidOCR
        with Image.open(BytesIO(image_bytes)) as image:
            image = image.convert('RGB')
            width, height = image.size
            pixels = np.asarray(image)[:, :, ::-1].copy()
        with _rapid_lock:
            if _rapid_engine is None:
                _rapid_engine = RapidOCR(params={
                    'Global.log_level': 'warning', 'Global.use_cls': False,
                    'EngineConfig.onnxruntime.intra_op_num_threads': 2,
                    'EngineConfig.onnxruntime.inter_op_num_threads': 1,
                })
            output = _rapid_engine(pixels, use_cls=False)
        blocks = []
        if output.boxes is not None and output.txts is not None:
            for box, text in zip(output.boxes, output.txts):
                if text.strip():
                    left, top = box.min(axis=0)
                    right, bottom = box.max(axis=0)
                    # Detector boxes contain padding. On flat UI backgrounds,
                    # recover actual glyph bounds so replacement type matches
                    # the source size rather than the padded detector height.
                    x0, y0 = max(0, int(left)), max(0, int(top))
                    x1, y1 = min(width, int(right)+1), min(height, int(bottom)+1)
                    crop = pixels[y0:y1, x0:x1]
                    if crop.size and crop.shape[0] > 3 and crop.shape[1] > 3:
                        corners = np.array([crop[0, 0], crop[-1, 0], crop[0, -1], crop[-1, -1]], dtype=float)
                        background = np.median(corners, axis=0)
                        if np.max(np.abs(corners-background)) < 20:
                            mask = np.max(np.abs(crop.astype(float)-background), axis=2) > 55
                            ys, xs = np.nonzero(mask)
                            if len(xs) > 3:
                                left, top = x0+int(xs.min()), y0+int(ys.min())
                                right, bottom = x0+int(xs.max())+1, y0+int(ys.max())+1
                    blocks.append(TextBlock(text, Rect(float(left), float(top), float(right-left), float(bottom-top))))
        return OcrResult(blocks, 'zh-en', width, height)
    except ImportError:
        raise OcrError('缺少 RapidOCR 组件，请重新安装依赖或在设置中选择 Windows OCR。') from None
    except OcrError:
        raise
    except Exception as exc:
        raise OcrError('本地 RapidOCR 识别失败，请检查模型文件或切换 Windows OCR。') from exc


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
