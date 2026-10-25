"""Live view of the ESP32-S3 camera board running SENSEWALK_cam_person, for aiming and demos.

    python test/cam_view.py --port COM8 --seconds 90

Opens a window showing what the camera sees plus the detector's verdict (PERSON / none, and
whether 2-of-3 frames confirm it). Close the window (or press q) to quit. About 2-3 frames per second.
"""
from __future__ import annotations

import argparse
import re
import time

import tkinter as tk

import cv2
import numpy as np
import serial
from PIL import Image, ImageTk

JPEG_RE = re.compile(rb"<<JPEG (\d+)>>\n")
LINE_RE = re.compile(r"infer=(\d+)ms person=(-?\d+) notperson=(-?\d+) -> (PERSON|none)( +\[CONFIRMED\])?")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM8")
    ap.add_argument("--seconds", type=float, default=90.0)
    args = ap.parse_args()

    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = args.port, 921600, 0.05
    ser.dtr = False
    ser.rts = False
    ser.open()
    ser.rts = True
    time.sleep(0.15)
    ser.rts = False

    buf = b""
    t0 = time.time()
    while time.time() - t0 < 15 and b"Ready." not in buf:
        buf += ser.read(4096)
    buf = b""

    root = tk.Tk()
    root.title("SENSEWALK camera (q to quit)")
    label_w = tk.Label(root, bg="black")
    label_w.pack()
    closed = []
    root.protocol("WM_DELETE_WINDOW", lambda: closed.append(1))
    root.bind("q", lambda e: closed.append(1))
    frame = np.zeros((240, 320, 3), np.uint8)
    verdict, confirmed, gap, infer = "waiting...", False, 0, 0
    last_req = 0.0
    t_end = time.time() + args.seconds
    while time.time() < t_end and not closed:
        if time.time() - last_req > 0.35:
            ser.write(b"c")
            last_req = time.time()
        buf += ser.read(65536)
        while True:
            m = JPEG_RE.search(buf)
            if m and len(buf) >= m.end() + int(m.group(1)):
                n = int(m.group(1))
                jpg = np.frombuffer(buf[m.end():m.end() + n], np.uint8)
                img = cv2.imdecode(jpg, cv2.IMREAD_COLOR)
                if img is not None:
                    frame = img
                buf = buf[:m.start()] + buf[m.end() + n:]
            else:
                break
        for line in buf.split(b"\n")[:-1]:
            lm = LINE_RE.search(line.decode(errors="replace"))
            if lm:
                infer, p, np_, verdict = int(lm.group(1)), int(lm.group(2)), int(lm.group(3)), lm.group(4)
                gap = p - np_
                confirmed = bool(lm.group(5))
        if b"\n" in buf and not JPEG_RE.search(buf):
            buf = buf.rsplit(b"\n", 1)[-1]
        view = cv2.resize(frame, (640, 480))
        color = (0, 200, 0) if confirmed else ((255, 165, 0) if verdict == "PERSON" else (200, 200, 200))
        label = f"{'PERSON CONFIRMED' if confirmed else verdict}   score gap {gap:+d}   {infer} ms"
        cv2.rectangle(view, (0, 0), (640, 36), (0, 0, 0), -1)
        cv2.putText(view, label, (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(view, cv2.COLOR_BGR2RGB)))
        label_w.configure(image=photo)
        label_w.image = photo
        root.update()
    ser.close()
    root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
