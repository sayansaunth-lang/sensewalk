"""Smoke test for the committed, trained ground-hazard model. Skipped when the
model file isn't present (e.g. a fresh clone that hasn't pulled it)."""
import numpy as np
import pytest

from vision.pi.src.detector import HAZARD_CLASSES_PATH, HAZARD_ONNX_PATH, YoloOnnxDetector

pytestmark = pytest.mark.skipif(
    not (HAZARD_ONNX_PATH.exists() and HAZARD_CLASSES_PATH.exists()),
    reason="trained hazard model not present in vision/pi/models/",
)


def test_class_file_lists_pothole():
    names = [line.strip() for line in HAZARD_CLASSES_PATH.read_text().splitlines() if line.strip()]
    assert "pothole" in names


def test_detector_loads_and_runs_on_blank_frame_without_error():
    detector = YoloOnnxDetector()
    blank = np.full((480, 640, 3), 127, dtype=np.uint8)
    result = detector.detect(blank)
    assert isinstance(result, list)
    for d in result:
        x1, y1, x2, y2 = d.box
        assert 0 <= x1 < x2 <= 640 and 0 <= y1 < y2 <= 480


def test_detector_handles_non_16_9_frames():
    detector = YoloOnnxDetector()
    for shape in [(240, 320, 3), (720, 1280, 3), (500, 500, 3)]:
        assert isinstance(detector.detect(np.zeros(shape, dtype=np.uint8)), list)
