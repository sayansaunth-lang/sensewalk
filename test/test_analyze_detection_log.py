import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyze_detection_log import ConfusionCounts, parse_bool_field  # noqa: E402


def test_parse_bool_field_variants():
    assert parse_bool_field("1") is True
    assert parse_bool_field("0") is False
    assert parse_bool_field("true") is True
    assert parse_bool_field("") is False


def test_confusion_counts_classification():
    counts = ConfusionCounts()
    counts.add(detected=True, truth=True)   # TP
    counts.add(detected=False, truth=False)  # TN
    counts.add(detected=True, truth=False)  # FP
    counts.add(detected=False, truth=True)  # FN

    assert counts.true_positive == 1
    assert counts.true_negative == 1
    assert counts.false_positive == 1
    assert counts.false_negative == 1
    assert counts.total == 4
    assert counts.accuracy == 0.5


def test_confusion_counts_rates_handle_zero_denominator():
    counts = ConfusionCounts()
    counts.add(detected=True, truth=True)
    assert counts.false_positive_rate == 0.0  # no actual negatives seen
    assert counts.false_negative_rate == 0.0


def test_end_to_end_against_synthetic_csv(tmp_path):
    csv_path = tmp_path / "detections.csv"
    csv_path.write_text(
        "timestamp,scenario,detected_hazard,ground_truth_hazard\n"
        "1,pothole,1,1\n"
        "2,pothole,0,1\n"
        "3,flat,0,0\n"
        "4,flat,1,0\n"
    )

    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "analyze_detection_log.py"), str(csv_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Overall" in result.stdout
    assert "true positive:  1" in result.stdout
