from __future__ import annotations

from dataclasses import replace
from urllib.parse import urlsplit

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QVBoxLayout, QWidget)

from .ocr import OcrError, available_languages
from .settings import Settings


LANGUAGES = [("简体中文", "zh-CN"), ("繁體中文", "zh-TW"), ("English", "en"),
             ("日本語", "ja"), ("한국어", "ko"), ("Français", "fr"),
             ("Deutsch", "de"), ("Español", "es"), ("Русский", "ru"),
             ("Português", "pt"), ("Italiano", "it"), ("ไทย", "th"),
             ("Tiếng Việt", "vi"), ("العربية", "ar")]


def language_combo(value: str, auto: bool = False) -> QComboBox:
    combo = QComboBox()
    if auto:
        combo.addItem("自动检测", "auto")
    for name, code in LANGUAGES:
        combo.addItem(name, code)
    index = combo.findData(value)
    combo.setCurrentIndex(max(0, index))
    return combo


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.original = settings
        self.result_settings = settings
        self.setWindowTitle("翻译设置")
        self.setMinimumWidth(550)
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        title = QLabel("让翻译适合你的工作方式")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        form = QFormLayout()
        form.setVerticalSpacing(16)
        self.provider = QComboBox()
        self.provider.addItem("谷歌公共接口 · 免 Key", "public")
        self.provider.addItem("Google Cloud Translation · 官方 API", "official")
        self.provider.setCurrentIndex(max(0, self.provider.findData(settings.provider)))
        form.addRow("翻译接口", self.provider)
        self.key = QLineEdit(settings.api_key)
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("也可设置环境变量 GOOGLE_TRANSLATE_API_KEY")
        form.addRow("Cloud API Key", self.key)
        self.proxy = QLineEdit(settings.proxy)
        self.proxy.setPlaceholderText("留空使用环境代理；例 http://127.0.0.1:7890")
        form.addRow("HTTP / HTTPS 代理", self.proxy)
        self.source = language_combo(settings.source_language, auto=True)
        form.addRow("原文语言", self.source)
        self.target = language_combo(settings.target_language)
        form.addRow('翻译为', self.target)
        self.engine = QComboBox()
        self.engine.addItem('RapidOCR · 本地中英混排', 'rapidocr')
        self.engine.addItem('Windows 系统 OCR', 'windows')
        self.engine.setCurrentIndex(max(0, self.engine.findData(settings.ocr_engine)))
        form.addRow('文字识别引擎', self.engine)
        self.ocr = QComboBox()
        self.ocr.addItem("系统识别语言", "auto")
        try:
            for code, name in available_languages():
                self.ocr.addItem(f"{name} ({code})", code)
        except OcrError:
            pass
        self.ocr.setCurrentIndex(max(0, self.ocr.findData(settings.ocr_language)))
        form.addRow("本地 OCR 语言", self.ocr)
        self.engine.currentIndexChanged.connect(lambda: self.ocr.setEnabled(self.engine.currentData() == 'windows'))
        self.ocr.setEnabled(settings.ocr_engine == 'windows')
        path_row = QWidget()
        path_layout = QHBoxLayout(path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        self.snipaste = QLineEdit(settings.snipaste_path)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self.browse)
        path_layout.addWidget(self.snipaste, 1)
        path_layout.addWidget(browse)
        form.addRow("Snipaste 程序", path_row)
        layout.addLayout(form)
        self.watch = QCheckBox("复制图片后自动翻译（适用于 Snipaste 截图）")
        self.watch.setChecked(settings.auto_translate_clipboard)
        layout.addWidget(self.watch)
        self.top = QCheckBox("结果窗口保持置顶")
        self.top.setChecked(settings.always_on_top)
        layout.addWidget(self.top)
        hint = QLabel("文字识别在本机完成，识别出的文字会发送至谷歌。\n"
                      "公共接口非官方承诺的 API，可能限流；官方 API 需启用服务及计费。\n"
                      "若无法连接谷歌，请配置可访问谷歌的 HTTP 代理。\n"
                      "Cloud Key 使用 Windows 加密后保存在本机。")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存设置")
        buttons.button(QDialogButtonBox.StandardButton.Save).setProperty("primary", True)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.provider.currentIndexChanged.connect(self.update_provider)
        self.update_provider()

    def update_provider(self):
        self.key.setEnabled(self.provider.currentData() == "official")

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 Snipaste.exe", self.snipaste.text(), "Snipaste (Snipaste.exe);;程序 (*.exe)")
        if path:
            self.snipaste.setText(path)

    def save(self):
        proxy = self.proxy.text().strip()
        if proxy:
            try:
                parsed = urlsplit(proxy)
                valid = parsed.scheme in {"http", "https"} and parsed.hostname and parsed.port
            except ValueError:
                valid = False
            if not valid:
                QMessageBox.warning(self, "代理地址有误", "请输入完整 HTTP 代理地址，例如 http://127.0.0.1:7890。")
                return
        settings = replace(self.original, provider=self.provider.currentData(),
                           ocr_engine=self.engine.currentData(),
                           api_key=self.key.text().strip(), proxy=proxy,
                           source_language=self.source.currentData(), ocr_language=self.ocr.currentData(),
                           target_language=self.target.currentData(),
                           snipaste_path=self.snipaste.text().strip(),
                           auto_translate_clipboard=self.watch.isChecked(), always_on_top=self.top.isChecked())
        try:
            settings.save()
        except (OSError, RuntimeError) as exc:
            QMessageBox.warning(self, "设置未保存", str(exc))
            return
        self.result_settings = settings
        self.accept()
