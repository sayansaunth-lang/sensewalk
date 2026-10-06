"""Decide when a detected fall is real enough to text someone.

The IMU rule is knowingly imperfect (the learning roadmap notes that sitting
down hard can trip it), and an SMS to family on every false alarm would teach
people to ignore the real one. So an alert is only sent when:

  1. the fall condition is active, AND
  2. nobody takes hold of the grips during a confirmation window.

A user who is fine simply grabs the handle and the alert is cancelled. A user
who is on the ground and not holding on (the case that matters) triggers it.
After one send the confirmer stays quiet until the fall condition clears, so a
single fall can never produce a stream of texts.
"""
from __future__ import annotations


class FallConfirmer:
    def __init__(self, confirm_window_s: float = 10.0) -> None:
        self.confirm_window_s = confirm_window_s
        self._started_at: float | None = None
        self._cancelled = False
        self._sent = False

    @property
    def counting_down(self) -> bool:
        return self._started_at is not None and not self._cancelled and not self._sent

    def seconds_left(self, now: float) -> float | None:
        if not self.counting_down:
            return None
        return max(0.0, self.confirm_window_s - (now - self._started_at))

    def observe(self, fall_active: bool, grip_present: bool, now: float) -> bool:
        """Call once per frame. Returns True exactly once per fall, at the moment
        the alert should be sent."""
        if not fall_active:
            self._started_at, self._cancelled, self._sent = None, False, False
            return False
        if self._sent or self._cancelled:
            return False
        if self._started_at is None:
            self._started_at = now
        if grip_present:
            self._cancelled = True
            return False
        if now - self._started_at >= self.confirm_window_s:
            self._sent = True
            return True
        return False


class FallLatch:
    """The ESP32 only ever reports `fall,1` (never `fall,0`), and only while its
    detection window is open. Without a latch the Pi would either see the flag for
    a split second or, if it simply stored it, stay in FALL_ALERT forever. This
    holds the flag for `hold_s` after the most recent report, then lets it clear.
    `hold_s` must be longer than the confirmation window or the alert would
    expire exactly as it is due to be sent."""

    def __init__(self, hold_s: float) -> None:
        self.hold_s = hold_s
        self._last: float | None = None

    def trigger(self, now: float) -> None:
        self._last = now

    def active(self, now: float) -> bool:
        return self._last is not None and (now - self._last) < self.hold_s
