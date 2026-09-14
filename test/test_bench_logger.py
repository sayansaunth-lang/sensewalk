import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bench_logger import BenchLogger  # noqa: E402

from comms.python import protocol  # noqa: E402


def test_bench_logger_labels_flat_ground_as_no_detection():
    logger = BenchLogger.__new__(BenchLogger)
    logger.scenario = "flat_ground"
    logger.rows = []
    logger.ground_truth_hazard = 0
    import threading

    logger._lock = threading.Lock()
    logger._tof_gnd_mm = 0
    logger._tof_gnd_baseline_mm = 0

    for i, distance in enumerate([300, 302, 298, 301, 299]):
        msg = protocol.decode(protocol.encode("tof_gnd", str(distance), i))
        logger._on_tof_gnd(msg)

    assert all(row["detected_hazard"] == 0 for row in logger.rows)
    assert all(row["ground_truth_hazard"] == 0 for row in logger.rows)


def test_bench_logger_detects_sudden_dropoff_and_records_marked_ground_truth():
    logger = BenchLogger.__new__(BenchLogger)
    logger.scenario = "pothole_15cm"
    logger.rows = []
    logger.ground_truth_hazard = 0
    import threading

    logger._lock = threading.Lock()
    logger._tof_gnd_mm = 0
    logger._tof_gnd_baseline_mm = 0

    # Establish a stable baseline first.
    for i, distance in enumerate([300] * 10):
        msg = protocol.decode(protocol.encode("tof_gnd", str(distance), i))
        logger._on_tof_gnd(msg)

    logger.ground_truth_hazard = 1  # tester marks the pothole as physically present
    msg = protocol.decode(protocol.encode("tof_gnd", "600", 10))  # +300mm jump
    logger._on_tof_gnd(msg)

    last_row = logger.rows[-1]
    assert last_row["detected_hazard"] == 1
    assert last_row["ground_truth_hazard"] == 1
