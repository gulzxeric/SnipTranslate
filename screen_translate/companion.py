"""One companion translation button beside the existing Snipaste toolbar.

No screenshot replacement, hotkey registration, code injection or changes to
Snipaste preferences. Native accessibility is used only for the toolbar and its
Copy button, when the user explicitly clicks Translate.
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QMessageBox, QSystemTrayIcon

from .dialogs import SettingsDialog, language_combo
from .google_translate import translate
from .ocr import recognize_image
from .settings import Settings
from .widgets import app_icon


class Signals(QObject):
    success = Signal(object)
    failure = Signal(str)


class Task(QRunnable):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.signals = Signals()

    def run(self):
        try:
            self.signals.success.emit(self.callback())
        except Exception as exc:
            logging.warning("Companion task failed: %s", str(exc))
            self.signals.failure.emit(str(exc))


class Companion(QObject):
    def __init__(self, application: QApplication, preferences: Settings):
        super().__init__()
        from .companion_widgets import FloatingTranslateButton, MiniResultWindow
        from .snipaste_native import NativeSnipaste
        self.app = application
        self.preferences = preferences
        self.native = NativeSnipaste(preferences.snipaste_path)
        from .coordinates import physical_to_logical
        self.button = FloatingTranslateButton(physical_to_logical=physical_to_logical)
        self.result = MiniResultWindow()
        from .image_result import ImageResultWindow
        self.image_result = ImageResultWindow()
        self.image_result.text_requested.connect(self.show_text)
        self.image_result.settings_requested.connect(self.settings)
        self.image_result.retry_requested.connect(self.retry)
        self.image_result.pin_requested.connect(self.pin_image)
        self._original_text = self._translated_text = ''
        self._capture_rect = None
        self._capture_log = None
        self.button.clicked.connect(self.copy_selected_image)
        self.result.retry_requested.connect(self.retry)
        self.result.settings_requested.connect(self.settings)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self._probe = None
        self._copy = None
        self._translation = None
        self._snipper = None
        self._probing = False
        self._busy = False
        self._waiting = False
        self._image = None
        self._ocr = None
        self._copy_sequence = 0
        self._last_problem = ""
        self._toolbar = None
        self._toolbar_snipper = 0
        self._toolbar_misses = 0
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.poll)
        self.clipboard_timer = QTimer(self)
        self.clipboard_timer.setInterval(100)
        self.clipboard_timer.timeout.connect(self.check_clipboard)
        self.copy_timeout = QTimer(self)
        self.copy_timeout.setInterval(4000)
        self.copy_timeout.setSingleShot(True)
        self.copy_timeout.timeout.connect(self.copy_failed)
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("Snipaste 翻译助手 · F1 框选后点击翻译")
        menu = QMenu()
        self.state_action = menu.addAction("等待 Snipaste 截图…")
        self.state_action.setEnabled(False)
        menu.addSeparator()
        menu.addAction("设置", self.settings)
        menu.addAction("查看最近译文", self.show_result)
        menu.addSeparator()
        menu.addAction("退出", self.quit)
        self.tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.settings() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()
        self.timer.start()

    def _task(self, callback, success, failure):
        task = Task(callback)
        task.signals.success.connect(success)
        task.signals.failure.connect(failure)
        self.pool.start(task)
        return task

    def poll(self):
        if self._probing or self._busy or self._waiting:
            if self._busy or self._waiting:
                self.button.hide()
            return
        self._probing = True
        cached_toolbar = self._toolbar
        cached_snipper = self._toolbar_snipper

        def probe():
            from .snipaste_native import probe_toolbar
            windows = self.native.snapshot()
            snippers = [w for w in windows if "snipper" in w.title.lower()]
            if not snippers:
                return None, None
            # This Snipaste build has a real HWND for the toolbar. Once its
            # structure has been verified, follow that window directly. UIA's
            # Offscreen property can flicker while Qt updates the selection.
            for window in snippers:
                if cached_toolbar and window.handle == cached_snipper:
                    live = next((w for w in windows if w.handle == cached_toolbar.handle
                                 and w.process_id == window.process_id), None)
                    if live:
                        return window, live
            for window in snippers:
                toolbar = probe_toolbar(window.handle)
                if toolbar:
                    return window, toolbar
            return snippers[0], None
        self._probe = self._task(probe, self.probed, self.probe_failed)

    def probed(self, result):
        self._probing = False
        snipper, toolbar = result
        self._snipper = snipper
        # Snipaste may hide/rebuild PaintBar while hovering annotation tools,
        # opening their palettes or moving quickly across its edge. A confirmed
        # selection belongs to the Snipper session, not PaintBar's visibility.
        if (snipper and not toolbar and self._toolbar
                and snipper.handle == self._toolbar_snipper
                and snipper.process_id == self._toolbar.process_id):
            toolbar = self._toolbar
        if toolbar and not self._busy and not self._waiting:
            self._toolbar = toolbar
            self._toolbar_snipper = snipper.handle
            self._toolbar_misses = 0
            self.button.set_anchor(toolbar.rect)
            if not self.button.isVisible():
                self.button.show()
            # Other Snipaste tool palettes can change the topmost Z order
            # without changing Qt's isVisible flag. Raise without taking focus.
            self.button.keep_above()
            self.state_action.setText("已连接 Snipaste 截图工具栏")
        else:
            self._toolbar = None
            self._toolbar_snipper = 0
            self.button.hide()
            self.state_action.setText("无法读取截图工具栏" if snipper else "等待 Snipaste 截图…")

    def probe_failed(self, message):
        self._probing = False
        self._toolbar_misses += 1
        if self._toolbar is None:
            self.button.hide()
        elif not self._busy and not self._waiting:
            self.button.keep_above()
        self._last_problem = message
        self.state_action.setText("连接失败：" + message[:55])

    def copy_selected_image(self):
        if not self._snipper or self._busy or self._waiting:
            return
        from .snipaste_native import request_copy
        from .capture_location import begin_capture_log
        self._capture_log = begin_capture_log(self.preferences.snipaste_path)
        self.button.hide()
        self._waiting = True
        self._copy_sequence = clipboard_sequence()
        handle = self._snipper.handle
        self._copy = self._task(lambda: request_copy(handle), self.copy_invoked, self.copy_error)

    def copy_invoked(self, ignored):
        self.clipboard_timer.start()
        self.copy_timeout.start()
        self.check_clipboard()

    def copy_error(self, message):
        self._waiting = False
        self.clipboard_timer.stop()
        self.copy_timeout.stop()
        self.result.set_error(message)
        self.result.raise_()
        self.result.activateWindow()

    def copy_failed(self):
        self.copy_error("未取得当前选区。请在 Snipaste 中选好范围后，再点击翻译。")

    def check_clipboard(self):
        if not self._waiting or clipboard_sequence() == self._copy_sequence:
            return
        image = QApplication.clipboard().image()
        if image.isNull():
            return
        self._waiting = False
        self.clipboard_timer.stop()
        self.copy_timeout.stop()
        self._image = image.copy()
        self._image.setDevicePixelRatio(1)
        from .capture_location import capture_rectangle
        from .coordinates import physical_to_logical
        self._capture_rect = capture_rectangle(self._capture_log, image.width(), image.height(), physical_to_logical)
        self._ocr = None
        self.image_result.set_source(self._image, self._capture_rect)
        self.start_translation()

    def start_translation(self):
        if self._image is None or self._busy:
            return
        from .common import image_bytes
        self._busy = True
        self.button.hide()
        self.image_result.show_busy()
        image = image_bytes(self._image)
        preferences = replace(self.preferences)
        existing = self._ocr

        def process():
            from .image_translation import paragraphs
            ocr = existing or recognize_image(image, preferences.ocr_language, preferences.ocr_engine)
            if not ocr.blocks:
                raise ValueError("没有识别到文字。请选取清晰文字，或在设置中选择对应 OCR 语言。")
            regions = paragraphs(ocr)
            result = translate([region.text for region in regions], target=preferences.target_language,
                               source=preferences.source_language, provider=preferences.provider,
                               api_key=preferences.effective_api_key, proxy=preferences.proxy)
            return ocr, regions, result
        self._translation = self._task(process, self.translated, self.translation_failed)

    def translated(self, pair):
        self._busy = False
        self._ocr, regions, result = pair
        self._original_text = self._ocr.text
        self._translated_text = '\n\n'.join(result.texts)
        from .image_translation import render
        try:
            image = render(self._image, regions, result.texts)
            self.image_result.set_result(image)
        except Exception as exc:
            self.image_result.set_error('图片排版失败：' + str(exc))

    def translation_failed(self, message):
        self._busy = False
        self.image_result.set_error(message)

    def retry(self):
        self.start_translation()

    def show_result(self):
        if self.image_result.has_image:
            self.image_result.reveal()
            return
        self.result.show()
        self.result.raise_()
        self.result.activateWindow()

    def show_text(self):
        self.result.set_result(self._original_text, self._translated_text)
        self.result.raise_()
        self.result.activateWindow()

    def pin_image(self, image):
        from .integration import _executable, _launch, IntegrationError
        QApplication.clipboard().setImage(image)
        self.image_result.close()
        try:
            _launch(_executable(self.preferences.snipaste_path), 'paste', '--clipboard')
        except IntegrationError as exc:
            self.result.set_error(str(exc))

    def settings(self):
        parent = self.image_result if self.image_result.isVisible() else self.result if self.result.isVisible() else None
        dialog = SettingsDialog(self.preferences, parent)
        from PySide6.QtCore import Qt
        dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        # Only translation options belong to this companion. No hotkeys or
        # automatic clipboard translation are offered here.
        dialog.watch.hide()
        dialog.top.hide()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            from .snipaste_native import NativeSnipaste
            previous = self.preferences
            self.preferences = dialog.result_settings
            if (previous.ocr_engine, previous.ocr_language) != (self.preferences.ocr_engine, self.preferences.ocr_language):
                self._ocr = None
            self.native = NativeSnipaste(self.preferences.snipaste_path)

    def quit(self):
        if self._busy or self._waiting:
            self.result.set_error("正在处理当前截图，完成后可退出。")
            self.show_result()
            return
        self.timer.stop()
        self.tray.hide()
        self.button.close()
        self.image_result.close()
        self.result.close()
        self.app.quit()


def clipboard_sequence() -> int:
    import ctypes
    return ctypes.windll.user32.GetClipboardSequenceNumber()


def main() -> int:
    parser = argparse.ArgumentParser(description="Snipaste 翻译助手：在原截图工具栏旁显示一个翻译按钮")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--diagnose", action="store_true")
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.diagnose:
        from .snipaste_native import _diagnose
        _diagnose(Settings.load().snipaste_path, True)
        return 0
    from .common import _configure_logging
    _configure_logging()
    application = QApplication(sys.argv[:1])
    application.setApplicationName("SnipasteTranslate")
    application.setApplicationDisplayName("Snipaste 翻译助手")
    application.setFont(QFont("Microsoft YaHei UI", 10))
    application.setStyle("Fusion")
    application.setQuitOnLastWindowClosed(False)
    if args.self_test:
        import json
        from concurrent.futures import ThreadPoolExecutor
        from PySide6.QtGui import QImage, QPainter, QColor
        from .common import image_bytes
        from .settings import config_path
        canvas = QImage(900, 150, QImage.Format.Format_RGB32)
        canvas.fill(QColor("white"))
        painter = QPainter(canvas)
        painter.setPen(QColor("black"))
        painter.setFont(QFont("Arial", 26))
        painter.drawText(30, 85, "Hello world! Download the document.")
        painter.end()
        def check():
            from .snipaste_native import _uia_session
            with _uia_session():
                pass
            ocr = recognize_image(image_bytes(canvas))
            if not ocr.blocks:
                raise RuntimeError("OCR self-test returned no text")
            from .image_translation import paragraphs, render
            regions = paragraphs(ocr)
            result = translate([region.text for region in regions])
            translated_image = render(canvas, regions, result.texts)
            if translated_image.isNull() or translated_image == canvas:
                raise RuntimeError('Translated image self-test failed')
            translated_image.save(str(config_path().parent / 'self-test-image.png'))
            return {"ok": True, "ocr": ocr.text, "translation": result.texts, "uia": True, 'image_translation': True}
        try:
            with ThreadPoolExecutor(max_workers=1) as worker:
                report = worker.submit(check).result(timeout=60)
        except Exception as exc:
            report = {"ok": False, "error": str(exc)}
        (config_path().parent / "self-test.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        return 0 if report["ok"] else 1
    socket = QLocalSocket()
    socket.connectToServer("SnipasteTranslate.Companion.v1")
    if not args.smoke_test and socket.waitForConnected(150):
        return 0
    server = QLocalServer()
    if not args.smoke_test:
        QLocalServer.removeServer("SnipasteTranslate.Companion.v1")
        server.listen("SnipasteTranslate.Companion.v1")
    companion = Companion(application, Settings.load())
    if args.smoke_test:
        companion.timer.stop()
        QTimer.singleShot(350, companion.quit)
    return application.exec()
