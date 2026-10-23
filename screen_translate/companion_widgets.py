"""Small, independent companion windows for the original Snipaste toolbar.

This module never observes or controls another application's windows. The owner
decides when the toolbar is visible, supplies coordinate conversion, and starts
the OCR/translation work when the floating button is clicked.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from ctypes import wintypes

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


PhysicalToLogical = Callable[[QPoint], QPoint]


class FloatingTranslateButton(QWidget):
    """A hidden-by-default, focus-preserving button beside Snipaste's toolbar.

    The owner must explicitly show/hide this window as the native toolbar comes
    and goes. ``move_to`` accepts Qt logical coordinates. ``set_anchor`` accepts
    UIA/Win32 physical coordinates and requires a mapper supplied by the owner's
    monitor/DPI layer; Qt screen origins alone cannot infer mixed-DPI native
    monitor rectangles reliably.
    """

    clicked = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        physical_to_logical: PhysicalToLogical | None = None,
    ):
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        super().__init__(parent, flags)
        self._physical_to_logical = physical_to_logical
        self.setObjectName("floatingTranslate")
        self.setWindowTitle("Snipaste 翻译")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(90, 34)
        self.setStyleSheet(
            "QWidget#floatingTranslate { background: transparent; }"
            "QPushButton#floatingTranslateAction { background: #08ad69; color: white;"
            " border: 1px solid #079d60; border-radius: 5px;"
            " font-family: 'Microsoft YaHei UI'; font-size: 14px; font-weight: 600;"
            " padding: 0; margin: 0; }"
            "QPushButton#floatingTranslateAction:hover { background: #07995d; }"
            "QPushButton#floatingTranslateAction:pressed { background: #07864f; }"
            "QPushButton#floatingTranslateAction:disabled { background: #98cbb4; border-color: #98cbb4; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.button = QPushButton("翻译", self)
        self.button.setObjectName("floatingTranslateAction")
        self.button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setToolTip("识别当前 Snipaste 选区并翻译")
        self.button.clicked.connect(lambda checked=False: self.clicked.emit())
        layout.addWidget(self.button)

    def move_to(self, position: QPoint) -> None:
        """Move without showing, activating, or changing native Snipaste focus."""
        self.move(position)

    def keep_above(self) -> None:
        """Restore stacking after native tool palettes open, preserving focus."""
        if os.name == "nt":
            import ctypes
            user = ctypes.WinDLL("user32", use_last_error=True)
            user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
            user.SetWindowPos.restype = wintypes.BOOL
            # HWND_TOPMOST, NOSIZE | NOMOVE | NOACTIVATE | NOOWNERZORDER.
            user.SetWindowPos(int(self.winId()), ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0213)
        else:
            self.raise_()

    def set_anchor(self, physical_rectangle: tuple[int, int, int, int]) -> None:
        """Place below/right-aligned with a physical-pixel toolbar rectangle.

        Set ``physical_to_logical`` in the constructor, or use ``move_to`` with
        already converted coordinates. Keep the whole button in the toolbar's
        screen work area, moving above the toolbar when it is near the bottom.
        """
        left, top, right, bottom = physical_rectangle
        if right <= left or bottom <= top:
            raise ValueError("工具栏矩形必须有正的宽度和高度。")
        if self._physical_to_logical is None:
            raise ValueError("set_anchor 需要屏幕 DPI 坐标转换函数；也可调用 move_to。")
        # Use the last pixel inside the rectangle: right/bottom themselves could
        # lie on a neighboring monitor with a different scaling factor.
        anchor = self._physical_to_logical(QPoint(right - 1, bottom - 1))
        position = QPoint(anchor.x() + 1 - self.width(), anchor.y() + 7)
        screen = QApplication.screenAt(anchor)
        if screen is not None:
            work_area = screen.availableGeometry()
            if position.y() + self.height() > work_area.bottom() + 1:
                toolbar_top = self._physical_to_logical(QPoint(left, top))
                position.setY(toolbar_top.y() - self.height() - 6)
            position.setX(max(work_area.left(), min(position.x(), work_area.right() + 1 - self.width())))
            position.setY(max(work_area.top(), min(position.y(), work_area.bottom() + 1 - self.height())))
        self.move_to(position)

    def nativeEvent(self, event_type, message):
        if os.name == "nt":
            native_message = wintypes.MSG.from_address(int(message))
            if native_message.message == 0x0021:  # WM_MOUSEACTIVATE
                return True, 3  # MA_NOACTIVATE: deliver click without focus.
        return super().nativeEvent(event_type, message)


class MiniResultWindow(QWidget):
    """Compact translation popup; only presents state supplied by its owner."""

    retry_requested = Signal()
    settings_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("miniTranslateResult")
        self.setWindowTitle("Snipaste 翻译")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.resize(420, 300)
        self.setMinimumSize(360, 260)
        self._original = ""
        self._translated = ""
        self._collapsed_height = 300
        self.setStyleSheet(
            "QWidget#miniTranslateResult { background: #f6f9f7; }"
            "QWidget#miniTranslateResult QLabel { color: #304a3c; background: transparent;"
            " font-family: 'Microsoft YaHei UI'; font-size: 12px; }"
            "QWidget#miniTranslateResult QLabel#resultStatus { font-size: 13px; font-weight: 600; }"
            "QWidget#miniTranslateResult QTextEdit { background: white; color: #243a2d;"
            " border: 1px solid #dce7df; border-radius: 7px; padding: 9px;"
            " font-family: 'Microsoft YaHei UI'; font-size: 14px; selection-background-color: #b9e6cd; }"
            "QWidget#miniTranslateResult QTextEdit#originalText { color: #63766b; font-size: 12px; }"
            "QWidget#miniTranslateResult QPushButton { color: #3d5848; background: white;"
            " border: 1px solid #d9e5dd; border-radius: 5px; padding: 6px 10px;"
            " font-family: 'Microsoft YaHei UI'; font-size: 12px; }"
            "QWidget#miniTranslateResult QPushButton:hover { background: #eaf5ee; border-color: #b1d7bf; }"
            "QWidget#miniTranslateResult QPushButton:disabled { color: #a4b1a9; background: #f0f4f1; }"
            "QWidget#miniTranslateResult QPushButton#copyTranslation { color: white; background: #08ad69; border-color: #08ad69; }"
            "QWidget#miniTranslateResult QPushButton#copyTranslation:hover { background: #07995d; }"
            "QWidget#miniTranslateResult QPushButton#copyTranslation:disabled { background: #a8d3bc; border-color: #a8d3bc; }"
            "QWidget#miniTranslateResult QToolButton { color: #6c8375; border: none;"
            " background: transparent; padding: 0; font-family: 'Microsoft YaHei UI'; font-size: 11px; }"
            "QWidget#miniTranslateResult QToolButton:hover { color: #078c55; }"
            "QWidget#miniTranslateResult QProgressBar { border: none; background: #e2eee6;"
            " max-height: 3px; border-radius: 1px; }"
            "QWidget#miniTranslateResult QProgressBar::chunk { background: #08ad69; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 13)
        layout.setSpacing(9)

        self.status_label = QLabel("翻译结果", self)
        self.status_label.setObjectName("resultStatus")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.translation_text = QTextEdit(self)
        self.translation_text.setReadOnly(True)
        self.translation_text.setAcceptRichText(False)
        self.translation_text.setPlaceholderText("译文会显示在这里")
        layout.addWidget(self.translation_text, 1)

        self.original_toggle = QToolButton(self)
        self.original_toggle.setText("显示原文 ▾")
        self.original_toggle.setCheckable(True)
        self.original_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.original_toggle.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.original_toggle.toggled.connect(self._toggle_original)
        self.original_toggle.hide()
        layout.addWidget(self.original_toggle)

        self.original_text = QTextEdit(self)
        self.original_text.setObjectName("originalText")
        self.original_text.setReadOnly(True)
        self.original_text.setAcceptRichText(False)
        self.original_text.setFixedHeight(80)
        self.original_text.hide()
        layout.addWidget(self.original_text)

        actions = QHBoxLayout()
        actions.setSpacing(7)
        self.copy_button = QPushButton("复制译文", self)
        self.copy_button.setObjectName("copyTranslation")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self._copy_translation)
        actions.addWidget(self.copy_button)
        actions.addStretch()
        self.retry_button = QPushButton("重试", self)
        self.retry_button.setEnabled(False)
        self.retry_button.clicked.connect(lambda checked=False: self.retry_requested.emit())
        actions.addWidget(self.retry_button)
        self.settings_button = QPushButton("设置", self)
        self.settings_button.clicked.connect(lambda checked=False: self.settings_requested.emit())
        actions.addWidget(self.settings_button)
        self.close_button = QPushButton("关闭", self)
        self.close_button.clicked.connect(self.close)
        actions.addWidget(self.close_button)
        for button in (self.copy_button, self.retry_button, self.settings_button, self.close_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addLayout(actions)

    def show_busy(self, message: str = "正在识别并翻译…") -> None:
        self._original = ""
        self._translated = ""
        self._collapse_original()
        self.original_toggle.hide()
        self.original_text.clear()
        self.translation_text.clear()
        self.translation_text.setPlaceholderText("请稍候，正在读取当前选区的文字…")
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: #3a6450;")
        self.progress.show()
        self.copy_button.setEnabled(False)
        self.retry_button.setEnabled(False)
        self.show()
        self.raise_()

    def set_result(self, original: str, translated: str) -> None:
        self._original = original
        self._translated = translated
        self.progress.hide()
        self.status_label.setText("翻译完成")
        self.status_label.setStyleSheet("color: #078d55;")
        self.translation_text.setPlainText(translated)
        self.original_text.setPlainText(original)
        self.original_toggle.setVisible(bool(original.strip()))
        self.copy_button.setEnabled(bool(translated.strip()))
        self.retry_button.setEnabled(True)
        self.show()

    def set_error(self, message: str) -> None:
        self._translated = ""
        self.progress.hide()
        self.status_label.setText("翻译未完成")
        self.status_label.setStyleSheet("color: #b2563d;")
        self.translation_text.setPlainText(message)
        self.copy_button.setEnabled(False)
        self.retry_button.setEnabled(True)
        self.show()

    def _copy_translation(self) -> None:
        if self._translated:
            QApplication.clipboard().setText(self._translated)

    def _collapse_original(self) -> None:
        if self.original_toggle.isChecked():
            self.original_toggle.setChecked(False)

    def _toggle_original(self, expanded: bool) -> None:
        self.original_text.setVisible(expanded)
        self.original_toggle.setText("收起原文 ▴" if expanded else "显示原文 ▾")
        if expanded:
            self._collapsed_height = self.height()
            self.resize(self.width(), self.height() + 89)
        else:
            self.resize(self.width(), max(self.minimumHeight(), self._collapsed_height))
