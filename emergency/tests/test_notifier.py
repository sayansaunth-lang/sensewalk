import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fakes import FakeModem, SteppingClock  # noqa: E402

from emergency.nmea import GpsReader  # noqa: E402
from emergency.notifier import EmergencyNotifier, numbers_from_env  # noqa: E402
from emergency.sim800 import Sim800  # noqa: E402

GGA = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47\r\n"
A, B = "+919876543210", "+911234567890"


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make(numbers=(A,), with_fix=True, modem=None, **kw):
    clock = Clock()
    gps = GpsReader(clock=clock)
    if with_fix:
        gps.feed(GGA.encode())
    m = modem or FakeModem()
    n = EmergencyNotifier(Sim800(m, clock=SteppingClock()), gps, list(numbers), clock=clock, **kw)
    return n, m, clock


def test_message_contains_maps_link_when_fix_is_fresh():
    n, _, _ = make()
    msg, used = n.build_message()
    assert used is True
    assert "https://maps.google.com/?q=48.117300,11.516667" in msg
    assert len(msg) <= 160


def test_no_fix_says_location_unavailable_rather_than_guessing():
    n, _, _ = make(with_fix=False)
    msg, used = n.build_message()
    assert used is False and "unavailable" in msg and "maps.google" not in msg


def test_stale_fix_is_not_used():
    n, _, clock = make(max_fix_age_s=60)
    clock.t += 500
    msg, used = n.build_message()
    assert used is False and "maps.google" not in msg


def test_sends_to_every_number():
    n, m, _ = make(numbers=(A, B))
    r = n.notify_fall()
    assert r.success and r.sent_to == [A, B] and not r.failed
    assert len(m.sms_bodies()) == 2


def test_cooldown_suppresses_repeats_then_allows_again():
    n, m, clock = make(cooldown_s=300)
    assert n.notify_fall() is not None
    assert n.notify_fall() is None            # still cooling down
    clock.t += 301
    assert n.notify_fall() is not None
    assert len(m.sms_bodies()) == 2


def test_failure_does_not_start_the_long_cooldown():
    m = FakeModem(handlers={})  # dead modem
    n, _, clock = make(modem=m, cooldown_s=300, retry_after_failure_s=30)
    r = n.notify_fall()
    assert r is not None and not r.success and A in r.failed
    assert n.notify_fall() is None            # brief back-off, not hammering
    clock.t += 31
    assert n.notify_fall() is not None        # retried long before the 300 s cooldown


def test_not_registered_is_reported_clearly():
    h = FakeModem.healthy()
    h["AT+CREG"] = b"\r\n+CREG: 0,2\r\n\r\nOK\r\n"
    n, _, _ = make(modem=FakeModem(handlers=h))
    r = n.notify_fall()
    assert not r.success and "not registered" in r.failed[A]


def test_one_number_failing_does_not_block_the_other():
    class Flaky(FakeModem):
        def write(self, data):
            if data.startswith(f'AT+CMGS="{A}"'.encode()):
                self.handlers["AT+CMGS"] = b"\r\nERROR\r\n"
            elif data.startswith(f'AT+CMGS="{B}"'.encode()):
                self.handlers["AT+CMGS"] = b"\r\n> "
            return super().write(data)

    n, _, _ = make(numbers=(A, B), modem=Flaky())
    r = n.notify_fall()
    assert r.sent_to == [B] and A in r.failed


def test_no_numbers_configured_does_nothing():
    n, m, _ = make(numbers=())
    assert n.notify_fall() is None and m.written == []


def test_numbers_from_env():
    assert numbers_from_env({"SENSEWALK_EMERGENCY_NUMBERS": f" {A} , {B},, "}) == [A, B]
    assert numbers_from_env({}) == []
