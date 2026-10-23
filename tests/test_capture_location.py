from PySide6.QtCore import QPoint, QRect
from screen_translate.capture_location import begin_capture_log, capture_rectangle


def test_only_new_matching_capture_is_used(tmp_path):
    path = tmp_path / 'splog.txt'
    path.write_text('Screenshot (0, 0, 600 x 400) destination: none\n')
    marker = begin_capture_log(str(tmp_path / 'Snipaste.exe'))
    assert capture_rectangle(marker, 600, 400, lambda p: p) is None
    with path.open('a') as stream:
        stream.write('Screenshot (-300, 150, 600 x 400) destination: clipboard\n')
    assert capture_rectangle(marker, 600, 400, lambda p: p) == QRect(-300, 150, 600, 400)
    assert capture_rectangle(marker, 601, 400, lambda p: p) is None


def test_unavailable_log_falls_back_to_center(tmp_path):
    marker = begin_capture_log(str(tmp_path / 'Snipaste.exe'))
    assert capture_rectangle(marker, 600, 400, lambda p: p) is None
