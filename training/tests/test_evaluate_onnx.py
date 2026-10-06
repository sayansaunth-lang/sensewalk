import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluate_onnx import average_precision, iou, match_image, precision_recall_at  # noqa: E402


def test_iou_basics():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(50 / 150)


def test_match_image_each_gt_claimed_once():
    gts = [(0, 0, 10, 10)]
    preds = [(0.9, (0, 0, 10, 10)), (0.8, (0, 0, 10, 10))]  # duplicate of same object
    res = match_image(preds, gts, 0.5)
    assert res == [(0.9, True), (0.8, False)]


def test_perfect_detector_has_ap_one():
    scored = [(0.9, True), (0.8, True), (0.7, True)]
    assert average_precision(scored, n_gt=3) == pytest.approx(1.0)


def test_ap_penalises_false_positives_ranked_high():
    good = average_precision([(0.9, True), (0.5, False)], n_gt=1)
    bad = average_precision([(0.9, False), (0.5, True)], n_gt=1)
    assert good > bad


def test_ap_zero_when_nothing_found():
    assert average_precision([(0.9, False)], n_gt=2) == 0.0
    assert average_precision([], n_gt=2) == 0.0


def test_precision_recall_at_threshold():
    scored = [(0.9, True), (0.6, False), (0.3, True)]
    r = precision_recall_at(scored, n_gt=3, conf_thr=0.5)
    assert (r["tp"], r["fp"], r["fn"]) == (1, 1, 2)
    assert r["precision"] == 0.5
    assert r["recall"] == pytest.approx(1 / 3, abs=1e-3)
