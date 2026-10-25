"""Watch the on-camera person detector (SENSEWALK_cam_person) and save what it sees.

    python test/cam_person_check.py --port COM8 --seconds 20 --out cam_person

Resets the board, prints a summary of the per-frame detections (speed, how often it says
PERSON), and saves the real photo ('c') and the exact 96x96 grayscale image given to the model
('g') so you can judge the camera view and the preprocessing by eye.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import serial

LINE_RE = re.compile(r"t=(\d+)ms infer=(\d+)ms person=(-?\d+) notperson=(-?\d+) -> (PERSON|none)( +\[CONFIRMED\])?")


def read_blob(ser: serial.Serial, header: re.Pattern, end: bytes, timeout: float):
    buf = b""
    t0 = time.time()
    while time.time() - t0 < timeout:
        buf += ser.read(65536)
        m = header.search(buf)
        if m:
            n = int(m.group(1)) if m.groups() else None
            start = m.end()
            if n is not None and len(buf) >= start + n:
                return buf[start:start + n]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM8")
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--out", default="cam_person")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = args.port, 921600, 0.2
    ser.dtr = False
    ser.rts = False
    ser.open()
    ser.rts = True
    time.sleep(0.15)
    ser.rts = False

    boot = b""
    t0 = time.time()
    while time.time() - t0 < 15 and b"Ready." not in boot and b"NOT READY" not in boot:
        boot += ser.read(4096)
    print("--- boot ---")
    for line in boot.decode(errors="replace").splitlines():
        if line.strip() and not line.startswith(("ESP-ROM", "Build", "SPIWP", "mode:", "load:", "entry")):
            print(line.strip()[:160].encode("ascii", "replace").decode())
    if b"Ready." not in boot:
        return 1

    stamp = int(time.time())
    for cmd, name in ((b"g", "gray"), (b"c", "photo")):
        ser.reset_input_buffer()
        ser.write(cmd)
        if cmd == b"g":
            raw = None
            buf = b""
            t1 = time.time()
            while time.time() - t1 < 6 and raw is None:
                buf += ser.read(65536)
                m = re.search(rb"<<GRAY 96x96>>\n", buf)
                if m and len(buf) >= m.end() + 96 * 96:
                    raw = buf[m.end():m.end() + 96 * 96]
            if raw:
                from PIL import Image
                path = out / f"gray96_{stamp}.png"
                Image.frombytes("L", (96, 96), raw).resize((288, 288), Image.NEAREST).save(path)
                print("saved", path)
            else:
                print("no gray frame received")
        else:
            data = read_blob(ser, re.compile(rb"<<JPEG (\d+)>>\n"), b"", 6)
            if data:
                path = out / f"photo_{stamp}.jpg"
                path.write_bytes(data)
                print("saved", path)
            else:
                print("no photo received")

    ser.reset_input_buffer()
    rows = []
    buf = b""
    t1 = time.time()
    while time.time() - t1 < args.seconds:
        buf += ser.read(4096)
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            m = LINE_RE.search(line.decode(errors="replace"))
            if m:
                rows.append((int(m.group(2)), int(m.group(3)), int(m.group(4)), m.group(5) == "PERSON", bool(m.group(6))))
    ser.close()

    if not rows:
        print("no detection lines received")
        return 1
    n = len(rows)
    infer = [r[0] for r in rows]
    print(f"\n--- {n} frames in {args.seconds:.0f}s ({n / args.seconds:.1f} fps) ---")
    print(f"inference time: avg {sum(infer) / n:.0f} ms, min {min(infer)}, max {max(infer)}")
    print(f"frames saying PERSON: {sum(r[3] for r in rows)} / {n}; CONFIRMED (2 of 3): {sum(r[4] for r in rows)} / {n}")
    print("person-notperson score gap: min %d max %d" % (min(r[1] - r[2] for r in rows), max(r[1] - r[2] for r in rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
