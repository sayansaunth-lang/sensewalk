import time

import pytest

from vision.pi.src.benchmark import make_frame, parse_throttled, percentile, suggest_every_n, time_calls


def test_time_calls_measures_and_counts_runs():
    calls = []

    def fn():
        calls.append(1)
        time.sleep(0.01)

    r = time_calls(fn, runs=5, warmup=2)
    assert len(calls) == 7  # 2 warm-up + 5 timed
    assert r["runs"] == 5
    assert 8 <= r["mean_ms"] <= 80  # generous: only checking it is in the right ballpark
    assert r["min_ms"] <= r["median_ms"] <= r["max_ms"]
    assert r["fps"] == pytest.approx(1000 / r["mean_ms"], rel=0.05)


def test_time_calls_rejects_zero_runs():
    with pytest.raises(ValueError):
        time_calls(lambda: None, runs=0)


def test_percentile():
    values = list(range(1, 101))
    assert percentile(values, 95) == 95
    assert percentile([7], 95) == 7


@pytest.mark.parametrize(
    "total_ms,cam_fps,expected",
    [(50, 15, 1), (66, 15, 1), (200, 15, 3), (600, 15, 9), (1000, 30, 30), (0, 15, 1)],
)
def test_suggest_every_n(total_ms, cam_fps, expected):
    assert suggest_every_n(total_ms, cam_fps) == expected


def test_parse_throttled_flags():
    ok = parse_throttled("throttled=0x0\n")
    assert ok == {"raw": "0x0", "under_voltage_now": False, "throttled_now": False,
                  "under_voltage_since_boot": False, "throttled_since_boot": False}
    bad = parse_throttled("throttled=0x50005")
    assert bad["under_voltage_now"] and bad["throttled_now"]
    assert bad["under_voltage_since_boot"] and bad["throttled_since_boot"]


def test_parse_throttled_garbage():
    assert parse_throttled("") is None
    assert parse_throttled("throttled=zzz") is None


def test_make_frame_shape():
    f = make_frame(320, 240)
    assert f.shape == (240, 320, 3)
