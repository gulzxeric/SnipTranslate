from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage


def image_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise ValueError("无法读取图片，请重新截图。")
    buffer.close()
    return bytes(data)


def _configure_logging():
    import logging
    from logging.handlers import RotatingFileHandler
    from .settings import config_path
    folder = config_path().parent
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folder / "app.log", maxBytes=500000, backupCount=1, encoding="utf-8")
    logging.basicConfig(handlers=[handler], level=logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")
