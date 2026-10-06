"""NEO-6M GPS support: NMEA sentence parsing and a fix tracker (D3 in the
learning roadmap).

Pure parsing code with no hardware dependency, so every behaviour is unit
tested against sentences with known-good coordinates. Only a position the GPS
itself marks as valid is ever accepted: a module with no satellite lock still
prints well-formed sentences full of empty or stale fields, and sending a
"location" built from those in an emergency SMS would be worse than sending none.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class GpsFix:
    latitude: float
    longitude: float
    satellites: Optional[int]
    received_at: float  # monotonic seconds when this fix was parsed


def checksum_ok(sentence: str) -> bool:
    """NMEA checksum: XOR of every character between '$' and '*', as 2 hex digits."""
    sentence = sentence.strip()
    if not sentence.startswith("$") or "*" not in sentence:
        return False
    body, _, given = sentence[1:].partition("*")
    calc = 0
    for ch in body:
        calc ^= ord(ch)
    try:
        return calc == int(given[:2], 16)
    except ValueError:
        return False


def parse_coordinate(value: str, hemisphere: str) -> Optional[float]:
    """NMEA gives (d)ddmm.mmmm. Returns signed decimal degrees, or None if malformed."""
    if not value or hemisphere not in ("N", "S", "E", "W"):
        return None
    try:
        dot = value.index(".")
        degrees = int(value[: dot - 2])
        minutes = float(value[dot - 2 :])
    except (ValueError, IndexError):
        return None
    if minutes >= 60:
        return None
    decimal = degrees + minutes / 60.0
    limit = 90 if hemisphere in ("N", "S") else 180
    if decimal > limit:
        return None
    return -decimal if hemisphere in ("S", "W") else decimal


def parse_sentence(line: str, now: float) -> Optional[GpsFix]:
    """Return a GpsFix for a valid GGA or RMC sentence that reports a real fix,
    otherwise None (wrong sentence type, bad checksum, no fix, malformed)."""
    line = line.strip()
    if not checksum_ok(line):
        return None
    fields = line[1 : line.index("*")].split(",")
    kind = fields[0][-3:]  # GPGGA / GNGGA / GPRMC ... -> GGA / RMC

    if kind == "GGA" and len(fields) >= 8:
        if fields[6] in ("", "0"):  # fix quality 0 = no fix
            return None
        lat, lon = parse_coordinate(fields[2], fields[3]), parse_coordinate(fields[4], fields[5])
        sats = int(fields[7]) if fields[7].isdigit() else None
    elif kind == "RMC" and len(fields) >= 7:
        if fields[2] != "A":  # A = valid, V = warning/void
            return None
        lat, lon = parse_coordinate(fields[3], fields[4]), parse_coordinate(fields[5], fields[6])
        sats = None
    else:
        return None

    if lat is None or lon is None:
        return None
    return GpsFix(latitude=lat, longitude=lon, satellites=sats, received_at=now)


class GpsReader:
    """Feed raw bytes from the GPS serial port in; read the latest valid fix out.
    Handles partial lines and discards junk, like comms.python.protocol.LineAssembler."""

    MAX_LINE = 200

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._buf = bytearray()
        self.last_fix: Optional[GpsFix] = None
        self.sentences_ok = 0
        self.sentences_rejected = 0

    def feed(self, data: bytes) -> None:
        self._buf.extend(data)
        while True:
            idx = self._buf.find(b"\n")
            if idx == -1:
                break
            raw = bytes(self._buf[:idx])
            del self._buf[: idx + 1]
            line = raw.decode("ascii", errors="ignore").strip()
            if not line.startswith("$"):
                continue
            fix = parse_sentence(line, self._clock())
            if fix is not None:
                self.last_fix = fix
                self.sentences_ok += 1
            else:
                self.sentences_rejected += 1
        if len(self._buf) > self.MAX_LINE:
            self._buf.clear()

    def fix_age_s(self) -> Optional[float]:
        return None if self.last_fix is None else self._clock() - self.last_fix.received_at

    def recent_fix(self, max_age_s: float) -> Optional[GpsFix]:
        age = self.fix_age_s()
        return self.last_fix if (age is not None and age <= max_age_s) else None

    def run(self, port, stop_event) -> None:
        """Blocking read loop for a background thread. `port` is anything with
        read(n) -> bytes (pyserial Serial opened with a short timeout)."""
        while not stop_event.is_set():
            data = port.read(256)
            if data:
                self.feed(data)
