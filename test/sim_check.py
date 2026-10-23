"""Check the simulated-sensor firmware over USB.

Flash the SIM build (CI artifact esp32s3-firmware, file SENSEWALK_ESP32_SIM.ino.merged.bin),
then run:

    python test/sim_check.py --port COM7 --seconds 45

The script listens like the Raspberry Pi would. The firmware mirrors every UART frame to
USB in simulation mode, so this decodes them with the real Python protocol codec (checksum
and sequence numbers verified) and also reads the human-readable [sim] log lines. It then
checks the scripted scenario produced the behaviour the safety rules require.

What this proves: the real firmware decision code, UART encoder and Python decoder agree on
a real ESP32-S3. What it does not prove: anything about real sensors, real brake hardware, or
the 50 ms end-to-end brake time (the "decision step" printed is only the software step).
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import serial  # noqa: E402

from comms.python import protocol  # noqa: E402

BRAKE_RE = re.compile(r"\[sim\] BRAKE (ENGAGED|released).*decision step (\d+) us")
PHASE_RE = re.compile(r"\[sim\] t=(\d+)s\s+phase (\d+): (.*)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM7")
    ap.add_argument("--seconds", type=float, default=45.0)
    args = ap.parse_args()

    ser = serial.Serial(args.port, 115200, timeout=0.2)
    ser.dtr = False
    ser.rts = False

    events: list[tuple[float, str]] = []  # (wall time, description)
    frames = bad = 0
    tags: dict[str, int] = {}
    seqs = protocol.SequenceTracker()
    gaps = 0
    engage_us: list[int] = []
    fall_msgs = 0
    brake_state_msgs: list[str] = []
    buf = b""
    t0 = time.time()
    while time.time() - t0 < args.seconds:
        buf += ser.read(1024)
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            text = line.decode(errors="replace").strip()
            if not text:
                continue
            now = time.time() - t0
            m = PHASE_RE.search(text)
            if m:
                events.append((now, f"phase {m.group(2)}: {m.group(3)}"))
                continue
            m = BRAKE_RE.search(text)
            if m:
                events.append((now, f"BRAKE {m.group(1)}"))
                if m.group(1) == "ENGAGED":
                    engage_us.append(int(m.group(2)))
                continue
            if "FALL detected" in text or "SIMULATED" in text:
                events.append((now, text))
                continue
            try:
                msg = protocol.decode(text)
            except (protocol.ChecksumError, protocol.MalformedLineError):
                if text.count(",") >= 3:  # looked like a frame but failed validation
                    bad += 1
                continue
            frames += 1
            tags[msg.tag] = tags.get(msg.tag, 0) + 1
            if seqs.observe(msg):
                gaps += 1
            if msg.tag == "fall":
                fall_msgs += 1
            if msg.tag == "brake_state":
                brake_state_msgs.append(msg.value)
    ser.close()

    print("\n=== timeline ===")
    for t, d in events:
        print(f"{t:6.1f}s  {d}")
    print("\n=== UART frames decoded on the laptop ===")
    print(f"valid frames: {frames}, failed validation: {bad}, sequence gaps: {gaps}")
    print("by tag:", dict(sorted(tags.items())))
    print("brake_state messages:", brake_state_msgs)

    engages = sum(1 for _, d in events if d == "BRAKE ENGAGED")
    releases = sum(1 for _, d in events if d == "BRAKE released")
    checks = [
        ("saw phases of the scenario", sum(1 for _, d in events if d.startswith("phase")) >= 8),
        ("brake engaged at least 3 times (forward ToF, drop-off, ultrasonic)", engages >= 3),
        ("brake released at least 3 times (needs hands on grips)", releases >= 3),
        ("fall rule fired and fall=1 reached the decoder", fall_msgs > 0),
        ("heartbeats decoded", tags.get("heartbeat", 0) > 0),
        ("telemetry decoded (tof_fwd, grip, imu)", all(tags.get(t, 0) > 0 for t in ("tof_fwd", "grip", "imu"))),
        ("brake_state 1/0 messages sent to the Pi", "1" in brake_state_msgs and "0" in brake_state_msgs),
        ("no checksum failures on decoded frames", bad == 0),
    ]
    print("\n=== checks ===")
    for name, ok in checks:
        print(("PASS  " if ok else "FAIL  ") + name)
    if engage_us:
        print(f"\nsoftware decision step on engage: {engage_us} microseconds "
              "(software only; NOT the sensor-to-brake time)")
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
