import numpy as np
import pytest

from vision.pi.src.detector import (
    Detection,
    find_ground_hazard,
    is_nearby,
    letterbox,
    nearest_person,
    postprocess_yolo_output,
)


def make_output(rows, nc=1):
    """Build a YOLOv8-style (1, 4+nc, N) tensor from rows of (cx, cy, w, h, *class_scores)."""
    arr = np.array(rows, dtype=np.float32)  # (N, 4+nc)
    return arr.T[None, ...]


def test_letterbox_preserves_aspect_and_pads():
    img = np.zeros((100, 200, 3), np.uint8)  # h=100, w=200 -> scale 1.6 at size 320
    padded, scale, pad_x, pad_y = letterbox(img, 320)
    assert padded.shape == (320, 320, 3)
    assert scale == pytest.approx(1.6)
    assert pad_x == 0
    assert pad_y == (320 - 160) // 2


def test_postprocess_maps_box_back_through_letterbox():
    # original frame 200x100 (w x h); letterboxed to 320: scale=1.6, pad_x=0, pad_y=80.
    # A box centred at original (100, 50), size 40x20 -> letterbox centre (160, 80+80=160), size 64x32.
    out = make_output([[160, 160, 64, 32, 0.9]])
    dets = postprocess_yolo_output(out, ["pothole"], scale=1.6, pad_x=0, pad_y=80, orig_w=200, orig_h=100)
    assert len(dets) == 1
    d = dets[0]
    assert d.label == "pothole"
    assert d.confidence == pytest.approx(0.9)
    x1, y1, x2, y2 = d.box
    assert (x1, y1, x2, y2) == (80, 40, 120, 60)


def test_postprocess_filters_low_confidence():
    out = make_output([[160, 160, 64, 32, 0.1]])
    assert postprocess_yolo_output(out, ["pothole"], 1.6, 0, 80, 200, 100, confidence_threshold=0.35) == []


def test_postprocess_nms_removes_overlapping_duplicates_keeps_best():
    out = make_output(
        [
            [160, 160, 64, 32, 0.9],
            [162, 160, 64, 32, 0.6],  # nearly identical box, lower score -> suppressed
            [300, 300, 20, 20, 0.8],  # far away -> kept
        ]
    )
    dets = postprocess_yolo_output(out, ["pothole"], 1.0, 0, 0, 320, 320)
    assert len(dets) == 2
    assert dets[0].confidence == pytest.approx(0.9)


def test_postprocess_accepts_channels_last_layout():
    out = make_output([[160, 160, 64, 32, 0.9]])  # (1, 5, 1)
    out_last = np.transpose(out, (0, 2, 1))  # (1, 1, 5)
    # A (1, N, 4+nc) tensor where N < 4+nc would be ambiguous; use several rows so it isn't.
    many = np.repeat(out_last, 10, axis=1)
    many[:, 1:, 4] = 0.0  # only the first row has a score
    dets = postprocess_yolo_output(many, ["pothole"], 1.0, 0, 0, 320, 320)
    assert len(dets) == 1


def test_postprocess_multiclass_picks_argmax():
    out = make_output([[100, 100, 40, 40, 0.2, 0.8]], nc=2)
    dets = postprocess_yolo_output(out, ["pothole", "stairs"], 1.0, 0, 0, 320, 320)
    assert dets[0].label == "stairs"


def test_postprocess_rejects_class_count_mismatch():
    out = make_output([[100, 100, 40, 40, 0.9]])
    with pytest.raises(ValueError):
        postprocess_yolo_output(out, ["pothole", "stairs"], 1.0, 0, 0, 320, 320)


def test_postprocess_clips_boxes_to_frame():
    out = make_output([[10, 10, 100, 100, 0.9]])  # extends past the top-left corner
    dets = postprocess_yolo_output(out, ["pothole"], 1.0, 0, 0, 320, 320)
    x1, y1, x2, y2 = dets[0].box
    assert x1 >= 0 and y1 >= 0 and x2 <= 320 and y2 <= 320


def test_is_nearby_uses_height_fraction():
    big = Detection("person", 0.9, (0, 0, 50, 300))
    small = Detection("person", 0.9, (0, 0, 20, 60))
    assert is_nearby(big, frame_height=480) is True
    assert is_nearby(small, frame_height=480) is False


def test_nearest_person_ignores_far_people_and_other_classes():
    dets = [
        Detection("person", 0.9, (0, 0, 20, 60)),     # far
        Detection("car", 0.99, (0, 0, 200, 400)),     # not a person
        Detection("person", 0.7, (0, 0, 80, 350)),    # near
        Detection("person", 0.8, (0, 0, 80, 250)),    # nearer-looking? smaller than 350 -> second
    ]
    best = nearest_person(dets, frame_height=480)
    assert best is not None and best.box[3] == 350
    assert nearest_person([Detection("person", 0.9, (0, 0, 20, 60))], 480) is None


def test_find_ground_hazard_picks_best_pothole():
    dets = [
        Detection("person", 0.99, (0, 0, 1, 1)),
        Detection("pothole", 0.5, (0, 0, 1, 1)),
        Detection("pothole", 0.8, (0, 0, 1, 1)),
    ]
    best = find_ground_hazard(dets)
    assert best is not None and best.confidence == 0.8
    assert find_ground_hazard([Detection("pothole", 0.2, (0, 0, 1, 1))]) is None


def test_rolling_confirm_needs_k_of_n():
    from vision.pi.src.detector import RollingConfirm

    rc = RollingConfirm(k=2, n=3)
    assert rc.observe(True) is False   # 1 of 1
    assert rc.observe(False) is False  # 1 of 2
    assert rc.observe(True) is True    # 2 of 3 -> confirmed
    assert rc.observe(False) is False  # window [F,T,F] -> 1 of 3


def test_rolling_confirm_single_flicker_never_confirms():
    from vision.pi.src.detector import RollingConfirm

    rc = RollingConfirm(k=2, n=3)
    results = [rc.observe(x) for x in (False, True, False, False, True, False, False)]
    assert not any(results)


def test_rolling_confirm_rejects_bad_params():
    from vision.pi.src.detector import RollingConfirm

    with pytest.raises(ValueError):
        RollingConfirm(k=4, n=3)
