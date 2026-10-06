"""Fall -> SMS with GPS location (D3 in the learning roadmap).

Policy decisions that matter in a real emergency, each covered by a test:

* A location is only included if the GPS has a RECENT valid fix. A stale
  position from five minutes ago could send helpers to the wrong place, so
  "location unavailable" is sent instead of a guess.
* A failed send never starts the cool-down. If the network was briefly down the
  alert must be retried; only a successful send suppresses repeats.
* After a success, repeats are suppressed for `cooldown_s` so one fall that keeps
  the IMU flag high does not send a text every frame.
* Phone numbers come from configuration (environment/CLI), never from source
  code, so they cannot be committed to a public repository by accident.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .nmea import GpsReader
from .sim800 import Sim800, Sim800Error

ENV_NUMBERS = "SENSEWALK_EMERGENCY_NUMBERS"  # comma-separated, e.g. "+919876543210,+911234567890"


def numbers_from_env(environ=os.environ) -> list[str]:
    raw = environ.get(ENV_NUMBERS, "")
    return [n.strip() for n in raw.split(",") if n.strip()]


@dataclass
class EmergencyResult:
    message: str
    used_location: bool
    sent_to: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return bool(self.sent_to)


class EmergencyNotifier:
    def __init__(
        self,
        gsm: Sim800,
        gps: Optional[GpsReader],
        numbers: list[str],
        cooldown_s: float = 300.0,
        retry_after_failure_s: float = 30.0,
        max_fix_age_s: float = 120.0,
        attempts_per_number: int = 2,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.gsm, self.gps, self.numbers = gsm, gps, list(numbers)
        self.cooldown_s = cooldown_s
        self.retry_after_failure_s = retry_after_failure_s
        self.max_fix_age_s = max_fix_age_s
        self.attempts_per_number = attempts_per_number
        self._clock = clock
        self._blocked_until = 0.0

    def build_message(self, headline: str = "SENSEWALK ALERT: possible fall detected.") -> tuple[str, bool]:
        fix = self.gps.recent_fix(self.max_fix_age_s) if self.gps else None
        base = headline
        if fix is None:
            return f"{base} Location unavailable (no recent GPS fix).", False
        age = int(self.gps.fix_age_s() or 0)
        sats = f", {fix.satellites} sats" if fix.satellites is not None else ""
        url = f"https://maps.google.com/?q={fix.latitude:.6f},{fix.longitude:.6f}"
        return f"{base} Location: {url} (fix {age}s old{sats})", True

    def notify_fall(self, headline: str = "SENSEWALK ALERT: possible fall detected.") -> Optional[EmergencyResult]:
        """Send the alert. Returns None when suppressed (no numbers configured or
        still cooling down), otherwise an EmergencyResult describing what happened.
        `headline` exists so the bench script can send a clearly-labelled TEST."""
        if not self.numbers:
            return None
        now = self._clock()
        if now < self._blocked_until:
            return None

        message, used_location = self.build_message(headline)
        result = EmergencyResult(message=message, used_location=used_location)

        try:
            if not self.gsm.ping():
                raise Sim800Error("modem not responding")
            if not self.gsm.registered():
                raise Sim800Error("not registered on a network (no 2G coverage, SIM, or antenna?)")
        except Sim800Error as exc:
            for n in self.numbers:
                result.failed[n] = str(exc)
            self._blocked_until = now + self.retry_after_failure_s
            return result

        for number in self.numbers:
            last_error = ""
            for _ in range(self.attempts_per_number):
                try:
                    self.gsm.send_sms(number, message)
                    result.sent_to.append(number)
                    break
                except Sim800Error as exc:
                    last_error = str(exc)
            else:
                result.failed[number] = last_error

        self._blocked_until = now + (self.cooldown_s if result.success else self.retry_after_failure_s)
        return result
