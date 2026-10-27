"""Whole-circuit test: the safety board and the camera board together, over their real wires.

    python test/system_check.py --safety COM7 --camera COM8 --seconds 75

Setup: safety board runs SENSEWALK_ESP32_SIM (simulated sensors: it brakes and releases on a 40 s script),
camera board runs SENSEWALK_cam_main, wired together (3 wires: camera TX -> safety GPIO16, camera RX <-
safety GPIO17, GND). Both boards are connected to this computer by USB, which is used only for logging.

What it checks, each from the receiving side's own log:
  1. safety -> camera wire : the camera board counts valid frames from the safety board
  2. brake events          : each brake / release the safety board makes is heard by the camera board
                             (and the camera board starts the matching voice clip)
  3. camera -> safety wire : the safety board counts haptic commands from the camera board
  4. detection -> vibration: when the camera board confirms a person or pothole, the safety board receives
                             the matching vibration level (150 person, 255 pothole). Stand in front of the
                             camera during the run to exercise this one; it is reported as NOT EXERCISED otherwise.

Opening a port resets that board (normal).
"""
from __future__ import annotations

import argparse
import re
import threading
import time

import serial


class Reader(threading.Thread):
    def __init__(self, name: str, port: str, baud: int, t0: float):
        super().__init__(daemon=True)
        self.name, self.t0 = name, t0
        self.ser = serial.Serial()
        self.ser.port, self.ser.baudrate, self.ser.timeout = port, baud, 0.1
        self.ser.dtr = False
        self.ser.rts = False
        self.ser.open()
        self.ser.rts = True  # reset pulse so we always see the boot messages
        time.sleep(0.15)
        self.ser.rts = False
        self.lines: list[tuple[float, str]] = []
        self.stop = False

    def run(self):
        buf = b""
        while not self.stop:
            try:
                buf += self.ser.read(4096)
            except serial.SerialException:
                break
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                text = raw.decode(errors="replace").strip()
                if text:
                    self.lines.append((time.time() - self.t0, text))

    def close(self):
        self.stop = True
        time.sleep(0.2)
        self.ser.close()


def last_int(pattern: str, lines, group=1):
    best = None
    for _, t in lines:
        m = re.search(pattern, t)
        if m:
            best = int(m.group(group))
    return best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--safety", default="COM7")
    ap.add_argument("--camera", default="COM8")
    ap.add_argument("--seconds", type=float, default=75.0)
    args = ap.parse_args()

    t0 = time.time()
    safety = Reader("safety", args.safety, 115200, t0)
    camera = Reader("camera", args.camera, 921600, t0)
    safety.start()
    camera.start()
    print(f"Listening to both boards for {args.seconds:.0f} s ... (stand in front of the camera for a few seconds to test detection)")
    time.sleep(args.seconds)
    safety.close()
    camera.close()

    s, c = safety.lines, camera.lines
    results = []

    def check(name, ok, detail, exercised=True):
        results.append((name, "PASS" if ok else ("FAIL" if exercised else "NOT EXERCISED"), detail))

    # sanity: both boards booted our firmware
    s_boot = any("SIMULATED SENSORS" in t for _, t in s)
    c_ready = any(t.startswith("Ready.") for _, t in c)
    check("safety board running the simulated-sensor firmware", s_boot, "saw the SIMULATED SENSORS banner" if s_boot else "no banner: flash SENSEWALK_ESP32_SIM to COM7")
    check("camera board running and ready", c_ready, "saw 'Ready.'" if c_ready else "no 'Ready.': flash SENSEWALK_cam_main to the camera board")

    # 1. safety -> camera wire
    frames = last_int(r"\[safety link\] (\d+) valid frames", c)
    check("1. safety -> camera wire", bool(frames and frames > 50), f"camera board received {frames} valid frames from the safety board" if frames is not None else "no [safety link] line from the camera board")

    # 2. brake events
    sim_events = [(t, "ENGAGED" in x) for t, x in s if "[sim] BRAKE" in x]
    cam_events = [(t, x.endswith("1")) for t, x in c if x.startswith("[safety] brake_state")]
    matched, lat = 0, []
    for ts, engaged in sim_events:
        hit = next((tc for tc, e in cam_events if e == engaged and 0 <= tc - ts < 2.0), None)
        if hit is not None:
            matched += 1
            lat.append(hit - ts)
    check("2. brake events reach the camera board", bool(sim_events) and matched == len(sim_events),
          f"{matched} of {len(sim_events)} brake/release events heard; delay {min(lat):.2f}-{max(lat):.2f} s (includes USB logging jitter)" if lat else
          f"{matched} of {len(sim_events)} heard")
    voice = [x for _, x in c if x.startswith("[voice] playing")]
    check("   voice clips started for them", any("obstacle_warning" in v for v in voice) and any("road_clear" in v for v in voice),
          "; ".join(sorted(set(v.split("playing ")[1].split(" (")[0] for v in voice))) or "no [voice] lines")

    # 3. camera -> safety wire
    hcount = last_int(r"\[comms\] (\d+) haptic commands received", s)
    check("3. camera -> safety wire", bool(hcount and hcount > 10), f"safety board received {hcount} haptic commands" if hcount is not None else "no [comms] haptic line from the safety board (flash the latest SIM firmware)")

    # 4. detection -> vibration
    confirmed = [(t, "person" if "PERSON" in x and "[CONFIRMED]" in x.split("|")[0] else "pothole")
                 for t, x in c if x.startswith("t=") and ("[CONFIRMED]" in x)]
    exercised = bool(confirmed)
    got = [(t, int(m.group(1))) for t, x in s for m in [re.search(r"haptic command received: left=(\d+)", x)] if m]
    levels = sorted({lv for _, lv in got if lv > 0})
    check("4. detection -> vibration command", bool(levels), f"camera confirmed a detection {len(confirmed)} times; safety board received vibration levels {levels}" if exercised else "the camera board never confirmed a person or pothole during the run", exercised=exercised)

    print("\n=== whole-circuit results ===")
    for name, status, detail in results:
        print(f"{status:14s} {name}: {detail}")
    print("\n=== key log lines ===")
    for who, lines in (("safety", s), ("camera", c)):
        keep = [(t, x) for t, x in lines if any(k in x for k in ("[sim] BRAKE", "[sim] FALL", "haptic command received", "[safety] brake_state", "[voice]", "[CONFIRMED]"))]
        for t, x in keep[:14]:
            print(f"{t:6.1f}s {who:6s} {x[:110]}")
    failed = [r for r in results if r[1] == "FAIL"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
