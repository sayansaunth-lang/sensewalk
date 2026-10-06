import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fakes import FakeModem, SteppingClock  # noqa: E402

from emergency.coordinator import EmergencyCoordinator  # noqa: E402
from emergency.fall_confirm import FallLatch  # noqa: E402
from emergency.nmea import GpsReader  # noqa: E402
from emergency.notifier import EmergencyNotifier  # noqa: E402
from emergency.sim800 import Sim800  # noqa: E402

NUM = "+919876543210"


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def make(modem=None, window=10.0):
    clock = Clock()
    m = modem or FakeModem()
    notifier = EmergencyNotifier(Sim800(m, clock=SteppingClock()), GpsReader(clock=clock), [NUM], clock=clock)
    coord = EmergencyCoordinator(notifier, window, runner=lambda fn: fn(), clock=clock)  # synchronous
    return coord, m, clock


def test_latch_holds_then_clears():
    latch = FallLatch(hold_s=15)
    assert not latch.active(0)
    latch.trigger(100)
    assert latch.active(110) and not latch.active(115.1)


def test_full_fall_sequence_sends_one_sms_and_reports_events():
    coord, m, clock = make()
    coord.report_fall()
    coord.update(grip_present=False)
    assert coord.pop_events() == ["countdown"]
    clock.t = 9
    coord.update(False)
    assert m.sms_bodies() == []
    clock.t = 10.5
    coord.update(False)
    assert len(m.sms_bodies()) == 1
    assert coord.pop_events() == ["sent"]
    clock.t = 12
    coord.update(False)
    assert len(m.sms_bodies()) == 1  # no repeat for the same fall


def test_grabbing_handle_during_countdown_sends_nothing():
    coord, m, clock = make()
    coord.report_fall()
    coord.update(False)
    clock.t = 5
    coord.update(grip_present=True)
    clock.t = 12
    coord.update(False)
    assert m.sms_bodies() == []
    assert coord.pop_events() == ["countdown"]


def test_alert_not_lost_to_latch_expiry():
    # latch hold (window + 5 s) must outlast the window, else the alert would expire as it is due
    coord, m, clock = make(window=10)
    coord.report_fall()
    for t in (0, 5, 9.9, 10.0):
        clock.t = t
        coord.update(False)
    assert len(m.sms_bodies()) == 1


def test_failed_send_is_reported():
    coord, _, clock = make(modem=FakeModem(handlers={}))
    coord.report_fall()
    coord.update(False)
    clock.t = 10.5
    coord.update(False)
    assert coord.pop_events() == ["countdown", "failed"]


def test_no_fall_means_silence():
    coord, m, clock = make()
    for t in range(0, 100, 5):
        clock.t = t
        coord.update(False)
    assert m.written == [] and coord.pop_events() == []
