"""Optional positioning from this Snipaste build's own capture log.

Read only bytes appended after our Copy request, and require exact bitmap
dimensions. If unavailable, the result viewer simply centers on the screen.
"""
from pathlib import Path
import re

from PySide6.QtCore import QPoint, QRect


def begin_capture_log(executable):
    path = Path(executable).parent / 'splog.txt'
    try:
        return path, path.stat().st_size
    except OSError:
        return path, 0


def capture_rectangle(marker, width, height, mapper):
    if not marker:
        return None
    path, offset = marker
    try:
        with path.open('rb') as stream:
            stream.seek(max(0, min(offset, path.stat().st_size)))
            text = stream.read(65536).decode('utf-8', errors='replace')
    except OSError:
        return None
    matches = re.findall(r'Screenshot\s*\((-?\d+),\s*(-?\d+),\s*(\d+)\s*x\s*(\d+)\)', text)
    for x, y, w, h in reversed(matches):
        if (int(w), int(h)) == (width, height):
            try:
                top = mapper(QPoint(int(x), int(y)))
                end = mapper(QPoint(int(x)+width-1, int(y)+height-1))
                return QRect(top.x(), top.y(), end.x()-top.x()+1, end.y()-top.y()+1)
            except RuntimeError:
                return None
    return None
