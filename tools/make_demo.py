"""Render a reproducible workflow illustration using the application's real widgets."""
from io import BytesIO
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication

from screen_translate.common import image_bytes
from screen_translate.companion_widgets import FloatingTranslateButton
from screen_translate.google_translate import translate
from screen_translate.image_result import ImageResultWindow
from screen_translate.image_translation import paragraphs, render
from screen_translate.ocr import recognize_image


def font(size, bold=False):
    value = QFont('Microsoft YaHei UI')
    value.setPixelSize(size)
    value.setBold(bold)
    return value


def make_demo():
    app = QApplication(['demo', '-platform', 'offscreen'])
    app.setFont(font(14))
    app.setStyle('Fusion')
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    source = QImage(860, 285, QImage.Format.Format_RGB32)
    source.fill(QColor('white'))
    painter = QPainter(source)
    painter.setPen(QColor('#182a22'))
    painter.setFont(font(32, True))
    painter.drawText(28, 54, 'Screenshot Translation')
    painter.setFont(font(22))
    painter.drawText(28, 110, 'Translate screenshots without leaving your work.')
    painter.drawText(28, 158, 'Press F1 to select text, then click Translate.')
    painter.drawText(28, 206, 'Press Esc to cancel and capture another region.')
    painter.setFont(font(18))
    painter.drawText(28, 254, 'Local OCR. Online translation. Keep the original layout.')
    painter.end()
    regions = paragraphs(recognize_image(image_bytes(source)))
    translated = translate([region.text for region in regions]).texts
    result = render(source, regions, translated)
    window = ImageResultWindow()
    window.set_source(source)
    button = FloatingTranslateButton()
    button.show()
    app.processEvents()
    button_image = button.grab().toImage()
    frames = []

    def arrange():
        window.resize(900, 370)
        window._image_rect = QRect(0, 0, 860, 285)
        window.toolbar.setGeometry(0, 300, 900, 55)
        app.processEvents()

    def frame(number, cn, en, content=None):
        image = QImage(1000, 640, QImage.Format.Format_RGB32)
        image.fill(QColor('#edf3f0'))
        p = QPainter(image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QColor('#16372a'))
        p.setFont(font(32, True))
        p.drawText(50, 52, 'SnipTranslate')
        p.setFont(font(15))
        p.setPen(QColor('#62766a'))
        p.drawText(50, 86, '操作示意 · 非测速 / Workflow illustration · not a speed benchmark')
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('white'))
        p.drawRoundedRect(QRect(44, 112, 912, 390), 12, 12)
        if content is None:
            p.drawImage(60, 128, source)
            p.setPen(QPen(QColor('#00c776'), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRect(59, 127, 862, 287))
            p.drawImage(QRect(830, 430, 90, 34), button_image)
        else:
            p.drawImage(60, 128, content)
        p.setPen(QColor('#16372a'))
        p.setFont(font(22, True))
        p.drawText(50, 550, f'{number}  {cn}')
        p.setFont(font(16))
        p.setPen(QColor('#62766a'))
        p.drawText(50, 584, en)
        p.end()
        frames.append(Image.open(BytesIO(image_bytes(image))).convert('RGB'))

    frame('01', 'F1 框选文字，点击绿色翻译按钮', 'Select text with Snipaste F1, then click Translate.')
    window.show_busy()
    window.set_progress('正在本地识别文字…')
    arrange()
    frame('02', '本地识别文字', 'OCR runs on your computer.', window.grab().toImage())
    window.set_progress('识别完成，正在调用谷歌翻译…')
    app.processEvents()
    frame('03', '谷歌翻译识别出的文字', 'Only recognized text is sent for online translation.', window.grab().toImage())
    window.set_result(result, '翻译完成')
    app.processEvents()
    frame('04', '原位置查看译图，可复制、保存或贴图', 'Read the translation in place; copy, save, or pin it.', window.grab().toImage())
    frames[-1].save(ROOT / 'docs' / 'screenshot.png')
    window.toggle.setChecked(False)
    app.processEvents()
    frame('05', '点击切换，随时对照原图', 'Switch between the original and translated image.', window.grab().toImage())
    window.set_source(source)
    window.show_busy()
    window.set_progress('按 Esc 或点击取消，可立即重新截图。')
    arrange()
    frame('06', '翻译中也可取消', 'Cancel while OCR or translation is still running.', window.grab().toImage())
    window.close()
    frame('07', 'Esc 返回截图，旧结果不会覆盖新结果', 'Press Esc and select another region. Stale results are ignored.')
    destination = ROOT / 'docs' / 'demo.gif'
    palette = [frame.convert('P', palette=Image.Palette.ADAPTIVE, colors=128) for frame in frames]
    palette[0].save(destination, save_all=True, append_images=palette[1:],
        duration=[1400, 850, 850, 2000, 1400, 1400, 1800], loop=0, optimize=True, disposal=2)
    button.close()
    print(f'Created {destination.name}: {destination.stat().st_size} bytes; {len(frames)} frames')


if __name__ == '__main__':
    (ROOT / 'docs').mkdir(exist_ok=True)
    make_demo()
