import time

from speech.buzzer_fallback import BuzzerFallback
from speech.phrases import Severity


def test_disarm_before_timeout_prevents_buzz(monkeypatch):
    fallback = BuzzerFallback(timeout_s=0.15)
    fired = []
    monkeypatch.setattr(fallback, "buzz", lambda severity=Severity.WARNING: fired.append(severity))

    fallback.arm(Severity.WARNING)
    time.sleep(0.05)
    fallback.disarm()
    time.sleep(0.3)

    fallback.close()
    assert fired == []


def test_watchdog_fires_when_not_disarmed(monkeypatch):
    fallback = BuzzerFallback(timeout_s=0.1)
    fired = []
    monkeypatch.setattr(fallback, "buzz", lambda severity=Severity.WARNING: fired.append(severity))

    fallback.arm(Severity.CRITICAL)
    time.sleep(0.35)

    fallback.close()
    assert fired == [Severity.CRITICAL]


def test_buzz_without_gpio_does_not_raise():
    fallback = BuzzerFallback(timeout_s=10)
    fallback._gpio = None  # simulate dev machine with no RPi.GPIO
    fallback.buzz(Severity.INFO)  # should log, not raise
    fallback.close()
