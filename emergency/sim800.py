"""SIM800L GSM modem driver: AT commands for registration check, signal
strength and sending an SMS (D3 in the learning roadmap).

Works with anything that looks like a pyserial port (write / read / in_waiting),
so the whole conversation is unit tested against a scripted fake modem.

Hardware facts that the code cannot fix for you:
  * SIM800L draws current spikes of up to ~2 A while transmitting. Power it from
    the battery/buck rail, NEVER from a microcontroller pin, or it browns out and
    resets mid-SMS.
  * It is a 2G modem. It only works where your carrier still runs a 2G network;
    check that before blaming the code.
"""
from __future__ import annotations

import re
import time
from typing import Callable, Optional

CTRL_Z = b"\x1a"
PHONE_RE = re.compile(r"^\+?[0-9]{6,15}$")
MAX_SMS_CHARS = 160  # single GSM-7 message


class Sim800Error(RuntimeError):
    """The modem returned an error, did not answer, or the request was invalid."""


def sanitize_sms_text(text: str) -> str:
    """Plain 7-bit ASCII only, no control characters, at most one SMS long.
    Anything outside GSM-7 would otherwise garble the message or split it into
    several billed parts in the middle of an emergency."""
    cleaned = "".join(ch if 32 <= ord(ch) < 127 else " " for ch in text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:MAX_SMS_CHARS]


class Sim800:
    def __init__(self, port, clock: Callable[[], float] = time.monotonic) -> None:
        self._port = port
        self._clock = clock

    # ------------------------------------------------------------ low level
    def _read_until(self, tokens: tuple[bytes, ...], timeout: float) -> bytes:
        deadline = self._clock() + timeout
        buf = b""
        while True:
            waiting = getattr(self._port, "in_waiting", 0)
            chunk = self._port.read(waiting or 1)
            if chunk:
                buf += chunk
                if any(t in buf for t in tokens):
                    return buf
            if self._clock() >= deadline:
                raise Sim800Error(f"timeout waiting for {tokens!r}; got {buf!r}")

    def _reset_input(self) -> None:
        while getattr(self._port, "in_waiting", 0):
            self._port.read(self._port.in_waiting)

    def command(self, cmd: str, timeout: float = 3.0) -> str:
        """Send an AT command, return the response text, raise on ERROR."""
        self._reset_input()
        self._port.write(cmd.encode("ascii") + b"\r")
        raw = self._read_until((b"OK", b"ERROR"), timeout)
        text = raw.decode("ascii", errors="replace")
        if "ERROR" in text:
            raise Sim800Error(f"{cmd!r} failed: {text.strip()!r}")
        return text

    # ------------------------------------------------------------ queries
    def ping(self, attempts: int = 3) -> bool:
        """True if the modem answers. Also turns echo off so replies are clean."""
        for _ in range(attempts):
            try:
                self.command("AT", timeout=1.0)
                self.command("ATE0", timeout=1.0)
                return True
            except Sim800Error:
                continue
        return False

    def registered(self) -> bool:
        """True when attached to the home network (1) or roaming (5)."""
        text = self.command("AT+CREG?")
        m = re.search(r"\+CREG:\s*\d+,\s*(\d+)", text)
        return bool(m and m.group(1) in ("1", "5"))

    def signal_quality(self) -> Optional[int]:
        """CSQ 0-31 (higher is better); None if unknown (99)."""
        m = re.search(r"\+CSQ:\s*(\d+)", self.command("AT+CSQ"))
        if not m:
            return None
        value = int(m.group(1))
        return None if value == 99 else value

    # ------------------------------------------------------------ SMS
    def send_sms(self, number: str, text: str, timeout: float = 40.0) -> None:
        """Send one text-mode SMS. Raises Sim800Error on any failure, so a caller
        can never mistake an unsent message for a sent one."""
        if not PHONE_RE.match(number):
            raise Sim800Error(f"invalid phone number {number!r}")
        message = sanitize_sms_text(text)
        if not message:
            raise Sim800Error("empty message")

        self.command("AT+CMGF=1")  # text mode
        self._reset_input()
        self._port.write(f'AT+CMGS="{number}"\r'.encode("ascii"))
        prompt = self._read_until((b">", b"ERROR"), timeout=5.0)  # wait for the message prompt
        if b">" not in prompt:
            raise Sim800Error(f"modem refused to start SMS: {prompt.decode('ascii', errors='replace').strip()!r}")
        self._port.write(message.encode("ascii") + CTRL_Z)
        raw = self._read_until((b"+CMGS:", b"ERROR"), timeout=timeout)
        if b"ERROR" in raw:
            raise Sim800Error(f"network rejected SMS: {raw.decode('ascii', errors='replace').strip()!r}")
