import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from emergency.nmea import GpsReader, checksum_ok, parse_coordinate, parse_sentence  # noqa: E402

# The standard worked examples from the NMEA 0183 documentation.
GGA = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"
RMC = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A"


def with_checksum(body: str) -> str:
    c = 0
    for ch in body:
        c ^= ord(ch)
    return f"${body}*{c:02X}"


def test_known_sentences_have_valid_checksums():
    assert checksum_ok(GGA)
    assert checksum_ok(RMC)


def test_corrupted_sentence_fails_checksum():
    assert not checksum_ok(GGA.replace("4807", "4808"))
    assert not checksum_ok("$GPGGA,no,star")
    assert not checksum_ok("GPGGA,123*47")


def test_parse_coordinate_hemispheres():
    assert parse_coordinate("4807.038", "N") == pytest.approx(48.1173)
    assert parse_coordinate("01131.000", "E") == pytest.approx(11.516667, abs=1e-5)
    assert parse_coordinate("4807.038", "S") == pytest.approx(-48.1173)
    assert parse_coordinate("01131.000", "W") == pytest.approx(-11.516667, abs=1e-5)


@pytest.mark.parametrize("val,hemi", [("", "N"), ("abc", "N"), ("4807.038", "X"), ("4875.000", "N"), ("9100.000", "N")])
def test_parse_coordinate_rejects_bad_input(val, hemi):
    assert parse_coordinate(val, hemi) is None


def test_gga_fix_parsed():
    fix = parse_sentence(GGA, now=5.0)
    assert fix is not None
    assert fix.latitude == pytest.approx(48.1173)
    assert fix.longitude == pytest.approx(11.516667, abs=1e-5)
    assert fix.satellites == 8
    assert fix.received_at == 5.0


def test_rmc_fix_parsed():
    fix = parse_sentence(RMC, now=1.0)
    assert fix is not None and fix.latitude == pytest.approx(48.1173)


def test_no_fix_sentences_are_rejected():
    assert parse_sentence(with_checksum("GPGGA,123519,,,,,0,00,99.9,,,,,,"), 0) is None  # quality 0
    assert parse_sentence(with_checksum("GPRMC,123519,V,,,,,,,230394,,"), 0) is None  # void
    assert parse_sentence(with_checksum("GPGSV,3,1,11,03,03,111,00"), 0) is None  # not a position sentence


def test_other_talker_ids_accepted():
    assert parse_sentence(with_checksum("GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,"), 0) is not None


def test_reader_handles_partial_lines_and_junk():
    t = [0.0]
    r = GpsReader(clock=lambda: t[0])
    data = ("garbage\r\n" + GGA + "\r\n").encode()
    r.feed(data[:25])
    assert r.last_fix is None
    r.feed(data[25:])
    assert r.last_fix is not None
    assert r.sentences_ok == 1


def test_reader_counts_rejected_and_keeps_last_good_fix():
    r = GpsReader(clock=lambda: 0.0)
    r.feed((GGA + "\r\n").encode())
    good = r.last_fix
    r.feed(b"$GPGGA,corrupt*00\r\n")
    assert r.last_fix is good
    assert r.sentences_rejected == 1


def test_recent_fix_expires():
    t = [100.0]
    r = GpsReader(clock=lambda: t[0])
    assert r.recent_fix(60) is None  # nothing yet
    r.feed((GGA + "\r\n").encode())
    t[0] = 130.0
    assert r.recent_fix(60) is not None
    t[0] = 200.0
    assert r.recent_fix(60) is None
    assert r.fix_age_s() == pytest.approx(100.0)
