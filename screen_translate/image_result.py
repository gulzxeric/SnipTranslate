"""Screenshot-position result canvas, with original/translation controls."""
from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QShortcut, QKeySequence
from PySide6.QtWidgets import QApplication, QWidget, QFrame, QHBoxLayout, QPushButton, QLabel, QFileDialog


class _Backdrop(QWidget):
    def __init__(self, screen, close):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setGeometry(screen.geometry())
        self._close = close

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 125))

    def mousePressEvent(self, event):
        self._close()


class ImageResultWindow(QWidget):
    text_requested = Signal()
    settings_requested = Signal()
    retry_requested = Signal()
    pin_requested = Signal(QImage)
    cancelled = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle('Snipaste 图片翻译')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.original = QImage()
        self.translated = QImage()
        self._backdrops = []
        self._image_rect = QRect()
        self._busy = False
        self._message = ''
        self._closed = False
        self.toolbar = QFrame(self)
        self.toolbar.setObjectName('imageToolbar')
        self.toolbar.setStyleSheet('QFrame#imageToolbar {background:white; border:1px solid #d8ddd9; border-radius:9px;}'
            'QPushButton {background:transparent; border:none; border-radius:5px; padding:9px 12px; color:#48514b; font:14px "Microsoft YaHei UI";}'
            'QPushButton:hover {background:#edf7f0;}'
            'QPushButton:checked {color:#00b86b; background:#eaf8ef;}'
            'QPushButton:disabled {color:#b5bcb8;}'
            'QLabel {color:#76837a; border:none; font:12px "Microsoft YaHei UI";}')
        row = QHBoxLayout(self.toolbar)
        row.setContentsMargins(9, 5, 9, 5)
        row.setSpacing(3)
        self.toggle = QPushButton('译图')
        self.toggle.setCheckable(True)
        self.toggle.setChecked(True)
        self.toggle.toggled.connect(self._toggle)
        row.addWidget(self.toggle)
        self.buttons = []
        for title, callback in [('复制', self.copy_image), ('保存', self.save_image), ('贴图', self.pin),
                                ('文字', self.text_requested.emit), ('重试', self.retry_requested.emit),
                                ('设置', self.settings_requested.emit), ('关闭', self.close)]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
            self.buttons.append(button)
        self.status = QLabel('')
        self.status.setMinimumWidth(90)
        row.insertWidget(0, self.status)
        self.toolbar.adjustSize()
        QShortcut(QKeySequence('Escape'), self, activated=self.close)
        QShortcut(QKeySequence('Ctrl+C'), self, activated=self.copy_image)
        QShortcut(QKeySequence('Ctrl+S'), self, activated=self.save_image)

    @property
    def has_image(self):
        return not self.original.isNull()

    def set_source(self, image, anchor=None):
        self.original = image.copy()
        self.original.setDevicePixelRatio(1)
        self.translated = QImage()
        self._closed = False
        self._anchor = anchor
        self._position()

    def _position(self):
        screen = QApplication.screenAt(self._anchor.center()) if self._anchor else QApplication.primaryScreen()
        screen = screen or QApplication.primaryScreen()
        work = screen.availableGeometry().adjusted(12, 12, -12, -12)
        self.toolbar.adjustSize()
        th = self.toolbar.sizeHint().height()
        tw = self.toolbar.sizeHint().width()
        if self._anchor:
            width, height = self._anchor.width(), self._anchor.height()
        else:
            width = round(self.original.width()/screen.devicePixelRatio())
            height = round(self.original.height()/screen.devicePixelRatio())
        ratio = min(1, work.width()/max(1, width), (work.height()-th-14)/max(1, height))
        width, height = max(1, round(width*ratio)), max(1, round(height*ratio))
        total_w = min(work.width(), max(width, tw))
        x = self._anchor.x() if self._anchor else work.center().x()-width//2
        y = self._anchor.y() if self._anchor else work.center().y()-(height+th)//2
        x = max(work.left(), min(x, work.right()-total_w+1))
        toolbar_above = y+height+th+12 > work.bottom()
        image_y = th+10 if toolbar_above else 0
        outer_y = y-image_y
        outer_y = max(work.top(), min(outer_y, work.bottom()-height-th-11))
        self.setGeometry(x, outer_y, total_w, height+th+12)
        self._image_rect = QRect(0, image_y, width, height)
        self.toolbar.setGeometry(max(0, total_w-tw), 0 if toolbar_above else height+10, min(tw, total_w), th)
        self.update()

    def reveal(self):
        if not self.has_image:
            return
        self._closed = False
        if not self._backdrops:
            self._backdrops = [_Backdrop(screen, self.close) for screen in QApplication.screens()]
            for backdrop in self._backdrops:
                backdrop.show()
        self.show()
        self.raise_()
        self.activateWindow()

    def show_busy(self):
        self._busy = True
        self._message = '正在本地识别并翻译…'
        self.status.setText('翻译中…')
        self.toggle.setEnabled(False)
        for button in self.buttons[:-2]:
            button.setEnabled(False)
        self.buttons[-1].setText('取消')
        self.reveal()
        self.update()

    def set_result(self, image, label='Google 翻译'):
        self.translated = image.copy()
        self._busy = False
        self._message = ''
        self.toggle.setChecked(True)
        self.toggle.setEnabled(True)
        for button in self.buttons:
            button.setEnabled(True)
        self.buttons[-1].setText('关闭')
        self.status.setText(label)
        self.update()

    def set_progress(self, message):
        if self._busy:
            self._message = message
            self.update()

    def set_error(self, text):
        self._busy = False
        self._message = text
        self.status.setText('翻译未完成')
        for button in self.buttons:
            button.setEnabled(True)
        self.buttons[-1].setText('关闭')
        self.update()

    def current_image(self):
        return self.translated if self.toggle.isChecked() and not self.translated.isNull() else self.original

    def _toggle(self, checked):
        self.toggle.setText('译图' if checked else '原图')
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self.has_image:
            painter.drawImage(self._image_rect, self.current_image())
            painter.setPen(QPen(QColor('#00c776'), 2))
            painter.drawRect(self._image_rect.adjusted(1, 1, -1, -1))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor('#00c776'))
            r = self._image_rect.adjusted(3, 3, -4, -4)
            for x, y in [(r.left(), r.top()), (r.center().x(), r.top()), (r.right(), r.top()),
                         (r.left(), r.center().y()), (r.right(), r.center().y()),
                         (r.left(), r.bottom()), (r.center().x(), r.bottom()), (r.right(), r.bottom())]:
                painter.drawRect(x-3, y-3, 6, 6)
        if self._message:
            box = self._image_rect.adjusted(14, 14, -14, -14)
            box.setHeight(min(box.height(), 80))
            painter.fillRect(box, QColor(255, 255, 255, 240))
            painter.setPen(QColor('#36523f'))
            painter.drawText(box.adjusted(12, 8, -12, -8), Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignVCenter, self._message)

    def copy_image(self):
        if self.has_image and not self._busy:
            QApplication.clipboard().setImage(self.current_image())
            self.status.setText('图片已复制')

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
        else:
            super().keyPressEvent(event)

    def save_image(self):
        if not self.has_image or self._busy:
            return
        path, _ = QFileDialog.getSaveFileName(self, '保存翻译图片', '译文截图.png', 'PNG 图片 (*.png)')
        if path:
            if not path.lower().endswith('.png'):
                path += '.png'
            self.status.setText('已保存' if self.current_image().save(path, 'PNG') else '保存失败')

    def pin(self):
        if self.has_image and not self._busy:
            self.pin_requested.emit(self.current_image().copy())

    def closeEvent(self, event):
        self._closed = True
        was_busy = self._busy
        self._busy = False
        if was_busy:
            self._message = ''
            self.status.setText('已取消')
            for button in self.buttons:
                button.setEnabled(True)
            self.buttons[-1].setText('关闭')
            self.toggle.setEnabled(not self.translated.isNull())
            self.cancelled.emit()
        for backdrop in self._backdrops:
            backdrop.close()
            backdrop.deleteLater()
        self._backdrops = []
        event.accept()
