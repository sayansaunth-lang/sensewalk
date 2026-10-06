"""Scripted stand-ins for the serial hardware, shared by the emergency tests."""
from __future__ import annotations


class SteppingClock:
    """Advances on every call, so timeout paths finish instantly in tests."""

    def __init__(self, step: float = 0.5) -> None:
        self.t, self.step = 0.0, step

    def __call__(self) -> float:
        self.t += self.step
        return self.t


class FakeModem:
    """A SIM800L that answers AT commands from a table. `handlers` maps a command
    prefix to the bytes to reply with; anything unhandled stays silent (a dead
    modem). Records everything written so tests can assert on the exact bytes."""

    def __init__(self, handlers: dict[str, bytes] | None = None, sms_reply: bytes = b"\r\n+CMGS: 7\r\n\r\nOK\r\n") -> None:
        self.handlers = handlers if handlers is not None else dict(self.healthy())
        self.sms_reply = sms_reply
        self.written: list[bytes] = []
        self._out = bytearray()

    @staticmethod
    def healthy() -> dict[str, bytes]:
        return {
            "AT+CMGF": b"\r\nOK\r\n",
            "AT+CREG": b"\r\n+CREG: 0,1\r\n\r\nOK\r\n",
            "AT+CSQ": b"\r\n+CSQ: 18,0\r\n\r\nOK\r\n",
            "AT+CMGS": b"\r\n> ",
            "ATE0": b"\r\nOK\r\n",
            "AT": b"\r\nOK\r\n",
        }

    # pyserial-like surface
    @property
    def in_waiting(self) -> int:
        return len(self._out)

    def write(self, data: bytes) -> int:
        self.written.append(bytes(data))
        if data.endswith(b"\x1a"):  # SMS body terminated by Ctrl-Z
            self._out += self.sms_reply
        elif data.endswith(b"\r"):
            cmd = data.decode("ascii").strip()
            for prefix in sorted(self.handlers, key=len, reverse=True):
                if cmd.startswith(prefix):
                    self._out += self.handlers[prefix]
                    break
        return len(data)

    def read(self, n: int = 1) -> bytes:
        chunk = bytes(self._out[:n])
        del self._out[:n]
        return chunk

    def commands(self) -> list[str]:
        return [w.decode("ascii", "replace").strip() for w in self.written if w.endswith(b"\r")]

    def sms_bodies(self) -> list[str]:
        return [w[:-1].decode("ascii") for w in self.written if w.endswith(b"\x1a")]
