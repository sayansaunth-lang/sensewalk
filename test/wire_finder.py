"""Find which camera-board pins are wired to the safety board, whatever pins you used.

    python test/wire_finder.py --safety COM7 --camera COM9

The safety board runs SENSEWALK_ESP32_SIM (it streams data out of GPIO17 all the time and logs the vibration
commands it receives on GPIO16). The camera board runs SENSEWALK_cam_main (>= the version with the 'w'
command). The script tells the camera board to scan its free pins and reads both boards' logs:

  * RX: the camera pin that reports valid frames is wired to the safety board's GPIO17 (TX)
  * TX: the safety board logs the marked vibration level it received; that level names the camera pin
        wired to the safety board's GPIO16 (RX)

It then says what to change. About 40 seconds. Ground must be connected for any of this to work.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from system_check import Reader  # noqa: E402

PINS = [1, 2, 14, 21, 38, 39, 40, 41, 42, 47, 48]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--safety", default="COM7")
    ap.add_argument("--camera", default="COM9")
    args = ap.parse_args()

    t0 = time.time()
    safety = Reader("safety", args.safety, 115200, t0)
    camera = Reader("camera", args.camera, 921600, t0)
    safety.start()
    camera.start()
    time.sleep(8)  # let both boards boot after the port reset
    camera.ser.write(b"w")
    print("Wire finder running on the camera board (about 25 s) ...")
    deadline = time.time() + 70
    while time.time() < deadline and not any("[wirefind] DONE" in t for _, t in camera.lines):
        time.sleep(0.5)
    time.sleep(1.5)
    safety.close()
    camera.close()

    rx = {}
    for _, t in camera.lines:
        m = re.search(r"\[wirefind\] RX GPIO(\d+): (\d+) valid frames", t)
        if m:
            rx[int(m.group(1))] = int(m.group(2))
    got_levels = sorted({int(m.group(1)) for _, t in safety.lines for m in [re.search(r"haptic command received: left=(\d+)", t)] if m and 100 <= int(m.group(1)) < 100 + len(PINS)})
    tx_pins = [PINS[lv - 100] for lv in got_levels]

    if not any("[wirefind] DONE" in t for _, t in camera.lines):
        print("The camera board did not finish the scan: flash the latest SENSEWALK_cam_main (the _cdc build for the native-USB connector).")
        return 2

    print("\n=== camera RX scan (which pin hears the safety board) ===")
    for p in PINS:
        print(f"  GPIO{p:2d}: {rx.get(p, '?')} valid frames")
    heard = [p for p, n in rx.items() if n > 5]
    print("\n=== camera TX scan (which pin the safety board heard) ===")
    print("  levels received by the safety board:", got_levels or "none", "-> camera pins", tx_pins or "none")

    print("\n=== result ===")
    ok = True
    if heard:
        print(f"safety TX (GPIO17) is wired to camera GPIO{heard[0]}" + ("" if heard[0] == 2 else "   <- not GPIO2: set kLinkRxPin to this in SENSEWALK_cam_main.ino"))
    else:
        ok = False
        print("NO camera pin heard the safety board. Check: the wire from safety GPIO17 is really connected to a camera-board pin, "
              "GND is connected between the boards, and the safety board is running SENSEWALK_ESP32_SIM.")
    if tx_pins:
        print(f"safety RX (GPIO16) is wired to camera GPIO{tx_pins[0]}" + ("" if tx_pins[0] == 1 else "   <- not GPIO1: set kLinkTxPin to this in SENSEWALK_cam_main.ino"))
    else:
        ok = False
        print("The safety board heard nothing from any camera pin. Check: the wire to safety GPIO16 is connected, "
              "GND is common, and TX goes to RX (the two signal wires must cross).")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
