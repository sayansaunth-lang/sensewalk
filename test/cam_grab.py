"""Grab photos from the ESP32-S3 camera board running SENSEWALK_cam_test.

    python test/cam_grab.py --port COM8 --count 3 --out cam_photos

Opening the port resets the board, so the script first waits for the "Ready" line (and prints
the boot messages, which say which camera pin map worked). Each photo is saved as a JPEG.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import serial


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM8")
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--out", default="cam_photos")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = args.port, args.baud, 0.3
    ser.dtr = False
    ser.rts = False
    ser.open()
    # Pulse the reset line (RTS -> EN on these boards) so we always see the boot messages.
    ser.rts = True
    time.sleep(0.15)
    ser.rts = False

    boot = b""
    t0 = time.time()
    while time.time() - t0 < 12 and b"Ready." not in boot and b"CAMERA FAILED" not in boot:
        boot += ser.read(4096)
    text = boot.decode(errors="replace")
    print("--- board says ---")
    for line in text.splitlines():
        if line.strip() and not line.startswith(("ESP-ROM", "Build", "SPIWP", "mode:", "load:", "entry")):
            print(line.strip()[:150].encode('ascii', 'replace').decode())
    if b"Ready." not in boot:
        print("Camera did not come up.")
        return 1

    saved = 0
    for i in range(args.count):
        ser.reset_input_buffer()
        ser.write(b"c")
        buf = b""
        t1 = time.time()
        while time.time() - t1 < 6:
            buf += ser.read(65536)
            m = re.search(rb"<<JPEG (\d+)>>\n", buf)
            if m:
                n = int(m.group(1))
                start = m.end()
                if len(buf) >= start + n:
                    jpg = buf[start:start + n]
                    if jpg[:2] == b"\xff\xd8" and jpg[-2:] == b"\xff\xd9":
                        path = out / f"cam_{int(time.time())}_{i}.jpg"
                        path.write_bytes(jpg)
                        print(f"saved {path} ({n} bytes)")
                        saved += 1
                    else:
                        print("frame arrived but is not a valid JPEG (corrupt transfer)")
                    break
        else:
            print("no frame received")
        time.sleep(0.5)
    return 0 if saved else 1


if __name__ == "__main__":
    sys.exit(main())
