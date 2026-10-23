from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QScrollArea, QSizePolicy, QWidget


def app_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#10a66b"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(2, 2, 60, 60), 17, 17)
    painter.setPen(QColor("white"))
    font = QFont("Microsoft YaHei UI", 26, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "译")
    painter.end()
    return QIcon(pixmap)


class EmptyArt(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(270, 170)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#d6e9e0"), 1))
        painter.setBrush(QColor("white"))
        painter.drawRoundedRect(QRectF(18, 20, 206, 124), 13, 13)
        painter.setBrush(QColor("#ecf8f1"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(36, 41, 112, 9), 4, 4)
        painter.drawRoundedRect(QRectF(36, 61, 166, 8), 4, 4)
        painter.drawRoundedRect(QRectF(36, 79, 140, 8), 4, 4)
        painter.setPen(QPen(QColor("#14ac72"), 2, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(28, 31, 184, 67), 4, 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#12a66e"))
        painter.drawRoundedRect(QRectF(159, 104, 90, 43), 11, 11)
        painter.setPen(QColor("white"))
        painter.setFont(QFont("Microsoft YaHei UI", 12, QFont.Weight.DemiBold))
        painter.drawText(QRectF(159, 104, 90, 43), Qt.AlignmentFlag.AlignCenter, "文 ⇄ A")
        painter.end()


class ImageViewer(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setObjectName("imageViewer")
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setWidget(self.label)
        self._image = QImage()
        self._fit = True

    def set_image(self, image: QImage):
        self._image = image.copy()
        self._update_pixmap()

    def set_fit(self, fit: bool):
        self._fit = fit
        self.setWidgetResizable(fit)
        self._update_pixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit:
            self._update_pixmap()

    def _update_pixmap(self):
        if self._image.isNull():
            return
        pixmap = QPixmap.fromImage(self._image)
        if self._fit:
            size = self.viewport().size() - QSize(36, 36)
            if size.width() > 0 and size.height() > 0:
                pixmap = pixmap.scaled(size.boundedTo(pixmap.size()), Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
        else:
            self.label.resize(pixmap.size() + QSize(36, 36))
        self.label.setPixmap(pixmap)
