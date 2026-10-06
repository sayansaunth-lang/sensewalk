import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from emergency.fall_confirm import FallConfirmer  # noqa: E402


def test_sends_once_after_window_with_no_grip():
    c = FallConfirmer(10)
    assert c.observe(True, False, 0) is False
    assert c.observe(True, False, 9.9) is False
    assert c.observe(True, False, 10.0) is True
    assert c.observe(True, False, 11.0) is False  # never twice for one fall


def test_grabbing_the_handle_cancels():
    c = FallConfirmer(10)
    c.observe(True, False, 0)
    assert c.observe(True, True, 4) is False       # user grabs on: cancelled
    assert c.observe(True, False, 20) is False     # even if they let go later in the same event


def test_rearms_after_fall_clears():
    c = FallConfirmer(5)
    c.observe(True, False, 0)
    assert c.observe(True, False, 5) is True
    c.observe(False, False, 6)                     # fall condition ended
    c.observe(True, False, 100)
    assert c.observe(True, False, 105) is True     # a new fall can alert again


def test_cancel_rearms_after_fall_clears_too():
    c = FallConfirmer(5)
    c.observe(True, True, 0)
    c.observe(False, False, 1)
    c.observe(True, False, 2)
    assert c.observe(True, False, 7) is True


def test_countdown_reporting():
    c = FallConfirmer(10)
    assert c.seconds_left(0) is None
    c.observe(True, False, 0)
    assert c.counting_down and c.seconds_left(4) == 6
    c.observe(True, True, 5)
    assert not c.counting_down and c.seconds_left(6) is None


def test_no_fall_never_sends():
    c = FallConfirmer(1)
    assert not any(c.observe(False, False, t) for t in range(100))
