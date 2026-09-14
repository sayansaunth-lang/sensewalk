"""Pi-side serial link to the ESP32: wraps pyserial, decodes lines via
protocol.py, tracks heartbeat liveness, and exposes the latest sensor
readings to the fusion state machine.

pyserial is imported lazily so the rest of the codebase (fusion tests,
vision pipeline) can be exercised on a dev machine with no serial hardware
and no pyserial installed.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import protocol

HEARTBEAT_TIMEOUT_S = 2.0
DEFAULT_BAUD = 115200


@dataclass
class LinkStats:
    messages_ok: int = 0
    messages_dropped_checksum: int = 0
    messages_dropped_malformed: int = 0
    last_heartbeat_at: Optional[float] = None
    gaps_by_tag: dict[str, int] = field(default_factory=dict)

    @property
    def mcu_alive(self) -> bool:
        if self.last_heartbeat_at is None:
            return False
        return (time.monotonic() - self.last_heartbeat_at) < HEARTBEAT_TIMEOUT_S


class SerialLink:
    """Usage:

        link = SerialLink("/dev/serial0")
        link.on_message("tof_gnd", lambda msg: ...)
        link.open()
        while True:
            link.poll()
    """

    def __init__(self, port: str, baud: int = DEFAULT_BAUD, timeout: float = 0.05) -> None:
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self._serial = None
        self._assembler = protocol.LineAssembler()
        self._tracker = protocol.SequenceTracker()
        self._handlers: dict[str, list[Callable[[protocol.Message], None]]] = {}
        self._seq_out = 0
        self.stats = LinkStats()

    def on_message(self, tag: str, handler: Callable[[protocol.Message], None]) -> None:
        self._handlers.setdefault(tag, []).append(handler)

    def open(self) -> None:
        import serial  # lazy import, see module docstring

        self._serial = serial.Serial(self.port, self.baud, timeout=self.timeout)

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def send(self, tag: str, value: str) -> None:
        if self._serial is None:
            raise RuntimeError("SerialLink not open() — call open() first")
        line = protocol.encode(tag, value, self._seq_out)
        self._seq_out = (self._seq_out + 1) % 65536
        self._serial.write(line)

    def poll(self) -> int:
        """Read whatever's available, decode complete lines, dispatch handlers.
        Returns the number of valid messages processed. Never raises on a
        malformed/corrupt line — those are counted in self.stats instead,
        per PROTOCOL.md error handling rules."""
        if self._serial is None:
            raise RuntimeError("SerialLink not open() — call open() first")
        data = self._serial.read(4096)
        if not data:
            return 0
        return self.feed(data)

    def feed(self, data: bytes) -> int:
        """Process raw bytes directly — used by poll() against a real port
        and by tests against synthetic byte streams."""
        processed = 0
        for line in self._assembler.feed(data):
            try:
                msg = protocol.decode(line)
            except protocol.ChecksumError:
                self.stats.messages_dropped_checksum += 1
                continue
            except protocol.MalformedLineError:
                self.stats.messages_dropped_malformed += 1
                continue

            self._tracker.observe(msg)
            self.stats.gaps_by_tag = self._tracker.gaps_by_tag
            self.stats.messages_ok += 1
            if msg.tag == "heartbeat":
                self.stats.last_heartbeat_at = time.monotonic()

            for handler in self._handlers.get(msg.tag, []):
                handler(msg)
            processed += 1
        return processed
