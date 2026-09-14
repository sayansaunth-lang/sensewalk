"""Piezo buzzer hard fallback (E1 in the learning roadmap).

Must fire even if the TTS engine crashes or lags — the roadmap's own test
for this module is "test this by deliberately killing the TTS process
mid-test", which means the fallback can't just be a try/except around the
TTS call in the same call stack (a hang there would hang the fallback too).

Instead this runs a watchdog on its own thread: AlertSpeaker.speak() (or
main.py) calls BuzzerFallback.arm(severity) right before attempting TTS,
and BuzzerFallback.disarm() right after TTS returns successfully. If
disarm() doesn't happen within the timeout, the watchdog thread fires the
buzzer itself, independent of whatever state the TTS call is stuck in.

Wired to a Pi GPIO pin per the BOM (not routed through the ESP32) so it
still works even if the UART link to the MCU is down.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from .phrases import Severity

DEFAULT_BUZZER_GPIO_PIN = 18
FALLBACK_TIMEOUT_S = 1.5

# Beep count scales with severity so a listener can distinguish "worth
# noting" from "stop now" without needing the speech to have landed.
BEEP_PATTERN_BY_SEVERITY = {
    Severity.INFO: 1,
    Severity.WARNING: 2,
    Severity.CRITICAL: 4,
}


class BuzzerFallback:
    def __init__(self, gpio_pin: int = DEFAULT_BUZZER_GPIO_PIN, timeout_s: float = FALLBACK_TIMEOUT_S) -> None:
        self.gpio_pin = gpio_pin
        self.timeout_s = timeout_s
        self._gpio = None
        self._armed_at: Optional[float] = None
        self._armed_severity: Severity = Severity.WARNING
        self._lock = threading.Lock()
        self._stop = threading.Event()

        try:
            import RPi.GPIO as GPIO  # lazy import — Pi-only hardware dependency

            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.gpio_pin, GPIO.OUT, initial=GPIO.LOW)
            self._gpio = GPIO
        except Exception as exc:  # pragma: no cover - depends on host GPIO availability
            print(f"[speech.buzzer_fallback] RPi.GPIO unavailable ({exc}); buzzer calls will log only")

        self._thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._thread.start()

    def arm(self, severity: Severity = Severity.WARNING) -> None:
        """Call immediately before attempting to speak an alert."""
        with self._lock:
            self._armed_at = time.monotonic()
            self._armed_severity = severity

    def disarm(self) -> None:
        """Call immediately after TTS successfully finishes speaking."""
        with self._lock:
            self._armed_at = None

    def _watchdog_loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                armed_at = self._armed_at
                severity = self._armed_severity
            if armed_at is not None and (time.monotonic() - armed_at) >= self.timeout_s:
                self.buzz(severity)
                with self._lock:
                    # Fired once for this arm cycle; wait for the next arm().
                    self._armed_at = None
            time.sleep(0.05)

    def buzz(self, severity: Severity = Severity.WARNING) -> None:
        """Fire the buzzer pattern directly — also usable stand-alone for
        the brake-engage / hazard events that always want an audible cue
        regardless of TTS state."""
        count = BEEP_PATTERN_BY_SEVERITY.get(severity, 1)
        if self._gpio is None:
            print(f"[speech.buzzer_fallback] (no GPIO) would buzz x{count} for {severity.name}")
            return
        for _ in range(count):
            self._gpio.output(self.gpio_pin, self._gpio.HIGH)
            time.sleep(0.1)
            self._gpio.output(self.gpio_pin, self._gpio.LOW)
            time.sleep(0.1)

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)
        if self._gpio is not None:
            self._gpio.cleanup(self.gpio_pin)
