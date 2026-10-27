"""Find which camera-board pins are wired to the safety board, whatever pins you used.

    python test/wire_finder.py --safety COM7 --camera COM9

The safety board runs SENSEWALK_ESP32_SIM (it streams data out of GPIO17 all the time and logs what it receives on
GPIO18). The camera board runs SENSEWALK_cam_main (the version with the 'w' command). The script tells the camera
board to scan its free pins and reads both boards' logs:

  * RX scan: for each camera pin, valid frames, raw bytes and signal edges. A pin wired to the safety board's TX
             (GPIO17) shows edges and frames. Edges or raw bytes without valid frames mean "connected but garbled".
  * TX scan: the camera board sends a marked vibration level out of each pin in turn; the safety board logs the
             level it received (that names the pin wired to its GPIO18) and counts raw bytes on that pin.

It then says what to change. About 40 seconds.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from system_check import Reader  # noqa: E402

PINS = [1, 2, 14, 21, 38, 39, 40, 41, 42, 43, 44, 47, 48]


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
    print("Wire finder running on the camera board (about 30 s) ...")
    deadline = time.time() + 80
    while time.time() < deadline and not any("[wirefind] DONE" in t for _, t in camera.lines):
        time.sleep(0.5)
    time.sleep(6)  # let the safety board print its next 5 s report
    safety.close()
    camera.close()

    if not any("[wirefind] DONE" in t for _, t in camera.lines):
        print("The camera board did not finish the scan: flash the latest SENSEWALK_cam_main (the _cdc build for the native-USB connector).")
        return 2

    rx = {}
    for _, t in camera.lines:
        m = re.search(r"\[wirefind\] RX GPIO(\d+): (\d+) valid frames(?:, (\d+) raw bytes, (\d+) edges)?", t)
        if m:
            rx[int(m.group(1))] = (int(m.group(2)), int(m.group(3) or 0), int(m.group(4) or 0))
    got_levels = sorted({int(m.group(1)) for _, t in safety.lines for m in [re.search(r"haptic command received: left=(\d+)", t)]
                         if m and 100 <= int(m.group(1)) < 100 + len(PINS)})
    tx_pins = [PINS[lv - 100] for lv in got_levels]
    raw_counts = [int(m.group(1)) for _, t in safety.lines for m in [re.search(r"\((\d+) raw bytes on the UART2 RX pin\)", t)] if m]
    safety_raw = max(raw_counts) if raw_counts else None

    print("\n=== camera RX scan (which pin hears the safety board's GPIO17) ===")
    for p in PINS:
        v, r, e = rx.get(p, (0, 0, 0))
        note = "  <== frames" if v > 5 else ("  <== signal activity (garbled?)" if (e > 100 or r > 5) else "")
        print(f"  GPIO{p:2d}: {v:3d} valid frames, {r:4d} raw bytes, {e:5d} edges{note}")
    heard = [p for p, (v, r, e) in rx.items() if v > 5]
    active = [p for p, (v, r, e) in rx.items() if v <= 5 and (e > 100 or r > 5)]

    print("\n=== camera TX scan (which pin the safety board's GPIO18 heard) ===")
    print("  vibration levels received by the safety board:", got_levels or "none", "-> camera pins", tx_pins or "none")
    print("  raw bytes seen on the safety board's UART2 RX pin:", safety_raw if safety_raw is not None else "(no report: flash the latest SENSEWALK_ESP32_SIM)")

    print("\n=== result ===")
    ok = True
    if heard:
        print(f"safety TX (GPIO17) -> camera GPIO{heard[0]}: OK" + ("" if heard[0] == 2 else "   (set kLinkRxPin = %d in SENSEWALK_cam_main.ino)" % heard[0]))
    elif active:
        ok = False
        print(f"Signal activity on camera GPIO{active} but no valid frames: the wire is there but the data is garbled "
              "(another chip driving the same pin, wrong baud, or noise).")
    else:
        ok = False
        print("No camera pin shows any signal from the safety board: the wire from safety GPIO17 is not reaching any scanned camera pin.")
    if tx_pins:
        print(f"camera GPIO{tx_pins[0]} -> safety GPIO18: OK" + ("" if tx_pins[0] == 1 else "   (set kLinkTxPin = %d in SENSEWALK_cam_main.ino)" % tx_pins[0]))
    elif safety_raw:
        ok = False
        print(f"The safety board's GPIO18 saw {safety_raw} raw bytes but no valid vibration command: connected but garbled.")
    else:
        ok = False
        print("The safety board's GPIO18 saw nothing from any camera pin.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
