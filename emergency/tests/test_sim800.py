import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fakes import FakeModem, SteppingClock  # noqa: E402

from emergency.sim800 import Sim800, Sim800Error, sanitize_sms_text  # noqa: E402


def modem(**kw):
    m = FakeModem(**kw)
    return m, Sim800(m, clock=SteppingClock())


def test_ping_ok_and_disables_echo():
    m, g = modem()
    assert g.ping() is True
    assert m.commands() == ["AT", "ATE0"]


def test_ping_false_when_modem_silent():
    m, g = modem(handlers={})
    assert g.ping(attempts=2) is False


@pytest.mark.parametrize("reply,expected", [(b"+CREG: 0,1", True), (b"+CREG: 0,5", True), (b"+CREG: 0,2", False), (b"+CREG: 0,0", False)])
def test_registration_states(reply, expected):
    h = FakeModem.healthy()
    h["AT+CREG"] = b"\r\n" + reply + b"\r\n\r\nOK\r\n"
    _, g = modem(handlers=h)
    assert g.registered() is expected


def test_signal_quality_and_unknown():
    _, g = modem()
    assert g.signal_quality() == 18
    h = FakeModem.healthy()
    h["AT+CSQ"] = b"\r\n+CSQ: 99,99\r\n\r\nOK\r\n"
    _, g2 = modem(handlers=h)
    assert g2.signal_quality() is None


def test_command_error_raises():
    h = FakeModem.healthy()
    h["AT+CREG"] = b"\r\nERROR\r\n"
    _, g = modem(handlers=h)
    with pytest.raises(Sim800Error):
        g.registered()


def test_send_sms_exact_byte_sequence():
    m, g = modem()
    g.send_sms("+919876543210", "Hello help")
    assert m.commands() == ["AT+CMGF=1", 'AT+CMGS="+919876543210"']
    assert m.sms_bodies() == ["Hello help"]
    assert m.written[-1].endswith(b"\x1a")


@pytest.mark.parametrize("bad", ["", "abc", "+91 98765", "12345", "+1234567890123456", "9876543210; AT+CMGD=1"])
def test_invalid_numbers_never_reach_the_modem(bad):
    m, g = modem()
    with pytest.raises(Sim800Error):
        g.send_sms(bad, "x")
    assert m.written == []


def test_empty_message_rejected():
    m, g = modem()
    with pytest.raises(Sim800Error):
        g.send_sms("+919876543210", "   \x00\x01 ")
    assert m.written == []


def test_network_rejection_raises():
    m, g = modem(sms_reply=b"\r\n+CMS ERROR: 331\r\n")
    with pytest.raises(Sim800Error):
        g.send_sms("+919876543210", "x")


def test_no_prompt_times_out():
    h = FakeModem.healthy()
    del h["AT+CMGS"]
    _, g = modem(handlers=h)
    with pytest.raises(Sim800Error):
        g.send_sms("+919876543210", "x")


def test_sanitize_ascii_and_length():
    assert sanitize_sms_text("café  ok\n\tnow") == "caf ok now"
    assert len(sanitize_sms_text("a" * 500)) == 160
    assert sanitize_sms_text("\x00\x07") == ""
