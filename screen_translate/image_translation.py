"""Paragraph-aware image translation with local background and type matching."""
from collections import Counter
from dataclasses import dataclass
from statistics import median

import numpy as np

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QTextLayout, QTextOption

from .models import OcrResult, Rect, TextBlock


@dataclass
class Region:
    blocks: list[TextBlock]

    @property
    def text(self):
        text = self.blocks[0].text
        for previous, block in zip(self.blocks, self.blocks[1:]):
            wrapped = block.rect.y >= previous.rect.y + previous.rect.height*.7
            if wrapped and text.endswith('-') and block.text[:1].islower():
                text = text[:-1] + block.text
            else:
                text += ' ' + block.text
        return text

    @property
    def rect(self):
        left = min(b.rect.x for b in self.blocks)
        top = min(b.rect.y for b in self.blocks)
        right = max(b.rect.x+b.rect.width for b in self.blocks)
        bottom = max(b.rect.y+b.rect.height for b in self.blocks)
        return Rect(left, top, right-left, bottom-top)


def paragraphs(ocr: OcrResult) -> list[Region]:
    regions = []
    for block in ocr.blocks:
        if regions:
            previous = regions[-1].blocks[-1].rect
            current = block.rect
            gap = current.y - previous.y - previous.height
            height = min(previous.height, current.height)
            overlap = min(previous.y+previous.height, current.y+current.height)-max(previous.y, current.y)
            horizontal_gap = current.x-previous.x-previous.width
            if (height > 0 and overlap >= height*.65 and 0 <= horizontal_gap <= height*1.2
                    and max(previous.height, current.height)/height < 1.3):
                regions[-1].blocks.append(block)
                continue
            if (height > 0 and max(previous.height, current.height) / height < 1.3
                    and 0 <= gap <= height * .9
                    and abs(regions[-1].rect.x-current.x) <= max(10, height*.65)):
                regions[-1].blocks.append(block)
                continue
        regions.append(Region([block]))
    return regions


def _rgb_view(image):
    # Keep the owning QImage alive alongside this strided, read-only view.
    # Unusual and premultiplied formats keep Qt's original pixel conversion.
    if image.format() not in (QImage.Format.Format_RGB32, QImage.Format.Format_ARGB32,
                              QImage.Format.Format_RGB888, QImage.Format.Format_RGBA8888):
        return None, None
    owner = image.convertToFormat(QImage.Format.Format_RGB888)
    pixels = np.ndarray((owner.height(), owner.width(), 3), dtype=np.uint8,
                        buffer=owner.constBits(), strides=(owner.bytesPerLine(), 3, 1))
    return owner, pixels


def _colors(image, region, pixels=None):
    r = region.rect
    perimeter = []
    for i in range(50):
        x = int(r.x + r.width*i/49)
        for y in (int(r.y-3), int(r.y+r.height+3)):
            if 0 <= x < image.width() and 0 <= y < image.height():
                c = image.pixelColor(x, y)
                perimeter.append((c.red()//8, c.green()//8, c.blue()//8))
    bucket = Counter(perimeter).most_common(1)[0][0] if perimeter else (31, 31, 31)
    background = QColor(*(min(255, n*8+7) for n in bucket))
    ink = []
    background_rgb = np.array(background.getRgb()[:3], dtype=np.int16) if pixels is not None else None
    for block in region.blocks:
        b = block.rect
        step = max(1, int((b.width*b.height/6000)**.5))
        if pixels is not None:
            y0, x0 = max(0, int(b.y)), max(0, int(b.x))
            y1 = max(y0, min(image.height(), int(b.y+b.height)+1))
            x1 = max(x0, min(image.width(), int(b.x+b.width)+1))
            crop = pixels[y0:y1:step, x0:x1:step]
            samples = crop.reshape(-1, 3)
            difference = np.abs(samples.astype(np.int16)-background_rgb).sum(axis=1)
            selected = samples[difference > 150]
            if len(selected):
                ink.append(selected)
            continue
        for y in range(max(0, int(b.y)), min(image.height(), int(b.y+b.height)+1), step):
            for x in range(max(0, int(b.x)), min(image.width(), int(b.x+b.width)+1), step):
                c = image.pixelColor(x, y)
                if sum(abs(a-z) for a, z in zip(c.getRgb()[:3], background.getRgb()[:3])) > 150:
                    ink.append(c.getRgb()[:3])
    if pixels is not None:
        foreground = QColor(*(int(n) for n in np.median(np.concatenate(ink), axis=0))) if ink else QColor('#202020')
    else:
        foreground = QColor(*(int(median([p[i] for p in ink])) for i in range(3))) if ink else QColor('#202020')
    return background, foreground


def _layout(text, width, size, bold=False):
    font = QFont('Microsoft YaHei UI')
    font.setPixelSize(size)
    font.setBold(bold)
    layout = QTextLayout(text, font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    layout.beginLayout()
    y = 0
    first = None
    last = None
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(max(1, width))
        line.setPosition(QPointF(0, y))
        first = first or line
        last = line
        y += line.height()
    layout.endLayout()
    metrics = QFontMetricsF(font)
    tight = metrics.tightBoundingRect(text[:80])
    offset = max(0, first.ascent()+tight.top()) if first else 0
    height = y-offset if last else 0
    return layout, height, offset


def render(image: QImage, regions: list[Region], translations: list[str]) -> QImage:
    if len(regions) != len(translations):
        raise ValueError('译文段落数量不匹配。')
    output = image.convertToFormat(QImage.Format.Format_RGB32).copy()
    pixel_owner, pixels = _rgb_view(image)
    painter = QPainter(output)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    bounds = QRectF(0, 0, image.width(), image.height())
    for region, translated in zip(regions, translations):
        if not translated.strip() or translated == region.text:
            continue
        r = region.rect
        background, foreground = _colors(image, region, pixels)
        line_height = median([b.rect.height for b in region.blocks])
        available = r.height + max(4, line_height*.4)
        for other in regions:
            o = other.rect
            if o.y >= r.y+r.height and min(r.x+r.width, o.x+o.width) > max(r.x, o.x):
                available = max(available, min(o.y-r.y-5, r.height+line_height*1.5))
                break
        available = min(available, image.height()-r.y)
        box = QRectF(r.x-1, r.y-1, r.width+3, available+1).intersected(bounds)
        chosen = None
        maximum = max(9, round(line_height*1.22))
        for size in range(maximum, 7, -1):
            layout, height, offset = _layout(translated, box.width(), size, line_height > 36)
            ink_height = QFontMetricsF(layout.font()).tightBoundingRect(translated[:80]).height()
            if ink_height > line_height*1.05:
                continue
            orphan = (layout.lineCount() > 1 and
                      layout.lineAt(layout.lineCount()-1).naturalTextWidth() < box.width()*.18)
            if height <= box.height() and not (orphan and size > maximum*.82):
                chosen = layout, height, offset
                break
        if chosen is None:
            chosen = _layout(translated, box.width(), 8, line_height > 36)
        # Cover original glyphs only; leave rules, icons and whitespace intact.
        for block in region.blocks:
            b = block.rect
            erase = QRectF(b.x-2, b.y-2, b.width+4, b.height+4).intersected(bounds)
            painter.fillRect(erase, background)
        layout, height, offset = chosen
        painter.save()
        painter.setClipRect(box)
        painter.setPen(foreground)
        layout.draw(painter, QPointF(box.x(), box.y()-offset))
        painter.restore()
    painter.end()
    return output
