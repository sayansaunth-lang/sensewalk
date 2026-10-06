#!/usr/bin/env python3
"""Bench check for the GPS + GSM hardware (D3 deliverable in the learning
roadmap: "one real SMS received on a phone, containing a real GPS coordinate").

Run it OUTDOORS with the antennas attached and the SIM800L powered from the
battery/buck rail (not a logic pin). It checks each stage and says which one
failed, so you are not guessing:

    python -m emergency.send_test_sms --gsm-port /dev/ttyUSB1 --gps-port /dev/ttyUSB0 --number +91XXXXXXXXXX

Pass your OWN number. The message is labelled as a test so nobody is alarmed.
Windows ports look like COM5. Omit --gps-port to test the SMS alone.
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from emergency.nmea import GpsReader  # noqa: E402
from emergency.notifier import EmergencyNotifier  # noqa: E402
from emergency.sim800 import Sim800, Sim800Error  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gsm-port", required=True)
    ap.add_argument("--gsm-baud", type=int, default=9600)
    ap.add_argument("--gps-port", default=None)
    ap.add_argument("--gps-baud", type=int, default=9600)
    ap.add_argument("--number", required=True, help="your own phone number, with country code")
    ap.add_argument("--wait-fix-s", type=float, default=180.0, help="how long to wait for a GPS fix (cold start can take minutes)")
    args = ap.parse_args()

    import serial  # pyserial, imported late so the module is importable without it

    gsm_port = serial.Serial(args.gsm_port, args.gsm_baud, timeout=0.2)
    gsm = Sim800(gsm_port)

    print("[1/4] modem answers AT ...", end=" ", flush=True)
    if not gsm.ping(attempts=5):
        print("FAIL\n  No reply. Check TX/RX wiring (crossed), baud rate, and that the module has its own power (up to ~2 A).")
        return 1
    print("ok")

    print("[2/4] network registration ...", end=" ", flush=True)
    try:
        registered = gsm.registered()
        signal = gsm.signal_quality()
    except Sim800Error as exc:
        print(f"FAIL ({exc})")
        return 1
    if not registered:
        print(f"FAIL (signal={signal})\n  Not registered. Check the SIM, the antenna, and that your carrier still runs a 2G network (SIM800L is 2G-only).")
        return 1
    print(f"ok (signal {signal}/31)")

    gps = None
    if args.gps_port:
        gps = GpsReader()
        gps_port = serial.Serial(args.gps_port, args.gps_baud, timeout=0.5)
        stop = threading.Event()
        threading.Thread(target=gps.run, args=(gps_port, stop), daemon=True).start()
        print(f"[3/4] waiting up to {args.wait_fix_s:.0f}s for a GPS fix (must be outdoors, clear sky) ...", flush=True)
        deadline = time.monotonic() + args.wait_fix_s
        while time.monotonic() < deadline and gps.last_fix is None:
            time.sleep(2)
            print(f"      still searching ... ({gps.sentences_ok} valid, {gps.sentences_rejected} rejected sentences)", flush=True)
        if gps.last_fix is None:
            print("  No fix. Indoors? Antenna connected? The SMS will say 'location unavailable'.")
        else:
            f = gps.last_fix
            print(f"      fix: {f.latitude:.6f}, {f.longitude:.6f} ({f.satellites} satellites)")
    else:
        print("[3/4] GPS skipped (no --gps-port)")

    print(f"[4/4] sending test SMS to {args.number} ...", end=" ", flush=True)
    notifier = EmergencyNotifier(gsm, gps, [args.number], cooldown_s=0)
    result = notifier.notify_fall(headline="SENSEWALK TEST (not an emergency).")
    if result is None or not result.success:
        print(f"FAIL: {result.failed if result else 'suppressed'}")
        return 1
    print("sent")
    print(f"      text: {result.message}")
    print("Now check your phone. Paste the link into a map to confirm the coordinate is where you are standing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
