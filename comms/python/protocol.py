"""ESP32 <-> Raspberry Pi UART protocol codec.

Wire format and message tags are defined in ../PROTOCOL.md — this module is
the single source of truth for the Pi-side implementation of that spec. Keep
it in sync with firmware/esp32/src/comms/uart_link.h if either side changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

MAX_LINE_LEN = 96


class ChecksumError(ValueError):
    """Raised when a decoded line's checksum does not match its payload."""


class MalformedLineError(ValueError):
    """Raised when a line does not have the minimum tag,value,seq,checksum shape."""


@dataclass(frozen=True)
class Message:
    """A single decoded protocol message."""

    tag: str
    value: str  # raw value field; caller splits on '|' for multi-field tags
    seq: int
    checksum: str

    def fields(self) -> list[str]:
        """Split a multi-field value (e.g. imu's pitch|roll|accel_mag) into parts."""
        return self.value.split("|")

    def int_value(self) -> int:
        return int(self.value)


def compute_checksum(tag: str, value: str, seq: int) -> str:
    """8-bit XOR of every byte in 'tag,value,seq', as 2 uppercase hex digits."""
    payload = f"{tag},{value},{seq}".encode("ascii")
    csum = 0
    for byte in payload:
        csum ^= byte
    return f"{csum:02X}"


def encode(tag: str, value: str, seq: int) -> bytes:
    """Build a wire-ready line (including trailing newline) for one message."""
    checksum = compute_checksum(tag, value, seq)
    line = f"{tag},{value},{seq},{checksum}\n"
    encoded = line.encode("ascii")
    if len(encoded) > MAX_LINE_LEN:
        raise ValueError(
            f"encoded message ({len(encoded)}B) exceeds MAX_LINE_LEN ({MAX_LINE_LEN}B): {line!r}"
        )
    return encoded


def decode(line: bytes | str) -> Message:
    """Parse and checksum-validate one line. Raises MalformedLineError /
    ChecksumError on bad input — callers should catch these and drop the
    frame rather than let a corrupt line propagate (see PROTOCOL.md error
    handling rules)."""
    if isinstance(line, bytes):
        text = line.decode("ascii", errors="replace")
    else:
        text = line
    text = text.strip("\r\n")

    parts = text.split(",")
    if len(parts) != 4:
        raise MalformedLineError(f"expected 4 comma-separated fields, got {len(parts)}: {text!r}")

    tag, value, seq_str, checksum = parts
    if not tag or not value or not checksum:
        raise MalformedLineError(f"empty field in line: {text!r}")

    try:
        seq = int(seq_str)
    except ValueError as exc:
        raise MalformedLineError(f"non-integer seq field: {seq_str!r}") from exc

    expected = compute_checksum(tag, value, seq)
    if checksum.upper() != expected:
        raise ChecksumError(f"checksum mismatch for {text!r}: expected {expected}, got {checksum}")

    return Message(tag=tag, value=value, seq=seq, checksum=checksum)


class LineAssembler:
    """Feed raw bytes from a serial port in; get back complete lines.

    Handles partial reads (a message split across two read() calls) and
    caps buffered-but-unterminated data at MAX_LINE_LEN so a dropped
    newline byte can't grow the buffer unboundedly (see PROTOCOL.md:
    'partial message' / 'dropped byte' handling).
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        self._buf.extend(data)
        lines: list[bytes] = []
        while True:
            idx = self._buf.find(b"\n")
            if idx == -1:
                break
            lines.append(bytes(self._buf[: idx + 1]))
            del self._buf[: idx + 1]
        if len(self._buf) > MAX_LINE_LEN:
            # No newline seen for a full frame's worth of bytes — the line is
            # corrupt/oversized. Drop it and resync on whatever comes next.
            self._buf.clear()
        return lines


class SequenceTracker:
    """Tracks per-tag sequence numbers to count gaps (drops) without ever
    blocking or rejecting a message because of a gap — sequence is
    informational only, per PROTOCOL.md."""

    def __init__(self) -> None:
        self._last_seq: dict[str, int] = {}
        self.gaps_by_tag: dict[str, int] = {}

    def observe(self, msg: Message) -> Optional[int]:
        """Returns the gap size (0 = consecutive) or None on the first message for this tag."""
        last = self._last_seq.get(msg.tag)
        self._last_seq[msg.tag] = msg.seq
        if last is None:
            return None
        expected = (last + 1) % 65536
        if msg.seq == expected:
            return 0
        gap = (msg.seq - expected) % 65536
        self.gaps_by_tag[msg.tag] = self.gaps_by_tag.get(msg.tag, 0) + gap
        return gap
