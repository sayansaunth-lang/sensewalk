import time

from vision.pi.src.camera import FPSCounter


def test_fps_counter_returns_zero_before_two_ticks():
    counter = FPSCounter()
    assert counter.tick() == 0.0


def test_fps_counter_reports_reasonable_rate():
    counter = FPSCounter(window=5)
    for _ in range(5):
        counter.tick()
        time.sleep(0.01)
    fps = counter.tick()
    assert fps > 0
    # 10ms sleeps -> ~100fps ceiling, generous bound to avoid flaky CI timing
    assert 1 <= fps <= 1000


def test_fps_counter_window_bounds_history():
    counter = FPSCounter(window=3)
    for _ in range(10):
        counter.tick()
    assert len(counter._timestamps) <= 3
