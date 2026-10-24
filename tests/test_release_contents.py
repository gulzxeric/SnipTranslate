from pathlib import Path
from tools.package_release import include_runtime_file


def test_release_keeps_core_runtime_and_recognition_models():
    for file in ['_internal/PySide6/Qt6Gui.dll', '_internal/PySide6/opengl32sw.dll',
                 '_internal/cv2/cv2.pyd', '_internal/PIL/_imaging.cp313-win_amd64.pyd',
                 '_internal/rapidocr/models/PP-OCRv6_rec_small.onnx',
                 '_internal/rapidocr/models/PP-OCRv6_det_small.onnx']:
        assert include_runtime_file(Path(file))


def test_release_omits_only_unused_video_avif_classifier_and_incompatible_icu():
    for file in ['_internal/cv2/opencv_videoio_ffmpeg500_64.dll',
                 '_internal/PIL/_avif.cp313-win_amd64.pyd',
                 '_internal/rapidocr/models/ch_ppocr_mobile_v2.0_cls_mobile.onnx',
                 '_internal/icuuc.dll.excluded']:
        assert not include_runtime_file(Path(file))
