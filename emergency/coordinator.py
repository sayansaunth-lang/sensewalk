"""Glue between the main loop and the emergency machinery: owns the fall
latch/confirmer, runs the (slow, 10 s+) SMS send off the frame loop, and hands
back plain-string events the loop can speak. Kept out of main.py so it is
testable without a camera, a model, or a modem."""
from __future__ import annotations

import queue
import threading
import time
from typing import Callable, Optional

from .fall_confirm import FallConfirmer, FallLatch
from .notifier import EmergencyNotifier


def _thread_runner(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


class EmergencyCoordinator:
    def __init__(
        self,
        notifier: EmergencyNotifier,
        confirm_window_s: float = 10.0,
        runner: Callable[[Callable[[], None]], None] = _thread_runner,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.notifier = notifier
        self.confirmer = FallConfirmer(confirm_window_s)
        self.latch = FallLatch(hold_s=confirm_window_s + 5.0)
        self._runner = runner
        self._clock = clock
        self._events: "queue.SimpleQueue[str]" = queue.SimpleQueue()
        self._announced_countdown = False

    def report_fall(self) -> None:
        """Call whenever the ESP32 reports `fall,1`."""
        self.latch.trigger(self._clock())

    @property
    def fall_active(self) -> bool:
        return self.latch.active(self._clock())

    def update(self, grip_present: bool) -> None:
        """Call once per frame."""
        now = self._clock()
        active = self.latch.active(now)
        if self.confirmer.observe(active, grip_present, now):
            self._runner(self._send)
        if self.confirmer.counting_down and not self._announced_countdown:
            self._announced_countdown = True
            self._events.put("countdown")
        if not active:
            self._announced_countdown = False

    def _send(self) -> None:
        result = self.notifier.notify_fall()
        if result is None:
            return
        self._events.put("sent" if result.success else "failed")

    def pop_events(self) -> list[str]:
        out = []
        while True:
            try:
                out.append(self._events.get_nowait())
            except queue.Empty:
                return out
