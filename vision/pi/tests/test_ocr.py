import numpy as np

from vision.pi.src.ocr import find_sign_like_regions, preprocess_for_ocr, should_attempt_ocr


def make_frame_with_rectangle(width=320, height=240, rect=(60, 90, 200, 60)):
    """A synthetic frame with a bright rectangle on a dark background,
    standing in for a sign/label in an otherwise empty scene."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    x, y, w, h = rect
    frame[y : y + h, x : x + w] = 255
    return frame


def test_preprocess_returns_binary_image_same_size():
    frame = make_frame_with_rectangle()
    processed = preprocess_for_ocr(frame)
    assert processed.shape[:2] == frame.shape[:2]
    unique_values = set(np.unique(processed).tolist())
    assert unique_values <= {0, 255}


def test_find_sign_like_regions_detects_synthetic_rectangle():
    frame = make_frame_with_rectangle()
    regions = find_sign_like_regions(frame, min_area_fraction=0.01)
    assert len(regions) >= 1


def test_should_attempt_ocr_false_on_blank_frame():
    blank = np.zeros((240, 320, 3), dtype=np.uint8)
    assert should_attempt_ocr(blank) is False


def test_should_attempt_ocr_true_with_sign_like_region():
    frame = make_frame_with_rectangle()
    assert should_attempt_ocr(frame) is True
