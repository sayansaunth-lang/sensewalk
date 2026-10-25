"""Measure the camera board's pothole detector end to end, using this laptop's screen as the "road".

    python test/cam_screen_test.py --data <merged dataset dir> --port COM8

Shows held-out pothole photos (never used in training) and held-out non-pothole views full screen, one at a
time, while the board's camera looks at the screen, and records what the board says about each. You aim the
camera at the screen so the photo fills its view (a 10 s countdown gives you time).

What it measures: the real board + real camera + real inference on photos it never trained on.
What it does not: real roads, real light, or a moving walker. A screen adds glare and a visible pixel grid.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import tkinter as tk
from pathlib import Path

import cv2
import numpy as np
import serial
from PIL import Image, ImageTk

LINE_RE = re.compile(r"pothole p=([0-9.]+) \((\d+)ms\) -> (POTHOLE|clear)( \[CONFIRMED\])?")
PERSON_RE = re.compile(r"person=(-?\d+) notperson=(-?\d+) -> (PERSON|none)")


def load_items(data: Path, per_class: int, seed: int):
    rng = np.random.default_rng(seed)
    pos, neg = [], []
    names = sorted((data / "images" / "test").glob("*.jpg"))
    rng.shuffle(names)
    for p in names:
        img = cv2.imread(str(p))
        if img is None:
            continue
        h, w = img.shape[:2]
        boxes = []
        lab = data / "labels" / "test" / (p.stem + ".txt")
        if lab.exists():
            for line in lab.read_text().splitlines():
                q = line.split()
                if len(q) == 5:
                    cx, cy, bw, bh = (float(v) for v in q[1:])
                    boxes.append(((cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h))
        if boxes and len(pos) < per_class:
            pos.append(("pothole photo " + p.name, img))
        # a negative: a square crop with no pothole box in it
        if len(neg) < per_class:
            short = min(h, w)
            for _ in range(40):
                side = rng.uniform(0.35, 0.7) * short
                x0, y0 = rng.uniform(0, w - side), rng.uniform(0, h - side)
                if all(min(x0 + side, b[2]) - max(x0, b[0]) <= 0 or min(y0 + side, b[3]) - max(y0, b[1]) <= 0 for b in boxes):
                    neg.append(("no-pothole crop of " + p.name, img[int(y0):int(y0 + side), int(x0):int(x0 + side)]))
                    break
        if len(pos) >= per_class and len(neg) >= per_class:
            break
    return pos, neg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--port", default="COM8")
    ap.add_argument("--per-class", type=int, default=15)
    ap.add_argument("--show-s", type=float, default=4.0)
    ap.add_argument("--out", type=Path, default=Path("cam_screen_test.json"))
    ap.add_argument("--threshold", type=float, default=0.73)
    args = ap.parse_args()

    pos, neg = load_items(args.data, args.per_class, 7)
    order = []
    for i in range(max(len(pos), len(neg))):  # alternate so drift in lighting hits both classes
        if i < len(pos):
            order.append((1, *pos[i]))
        if i < len(neg):
            order.append((0, *neg[i]))

    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = args.port, 921600, 0.05
    ser.dtr = False
    ser.rts = False
    ser.open()
    ser.rts = True
    time.sleep(0.15)
    ser.rts = False

    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.configure(bg="black")
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    label = tk.Label(root, bg="black", fg="white", font=("Segoe UI", 28))
    label.pack(expand=True, fill="both")

    def show_text(text):
        label.configure(image="", text=text)
        label.image = None
        root.update()

    def show_img(img):
        h, w = img.shape[:2]
        s = min(sw / w, sh / h) * 0.95
        view = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
        photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(view, cv2.COLOR_BGR2RGB)))
        label.configure(image=photo, text="")
        label.image = photo
        root.update()

    buf = b""
    t0 = time.time()
    while time.time() - t0 < 15 and b"Ready." not in buf:
        buf += ser.read(4096)
        root.update()
    buf = b""
    for sec in range(10, 0, -1):
        show_text(f"Aim the camera board at this screen so each photo fills its view.\nStarting in {sec} s ...")
        end = time.time() + 1
        while time.time() < end:
            ser.read(4096)
            root.update()

    results = []
    for k, (is_pos, name, img) in enumerate(order):
        show_img(img)
        ps, confirmed, persons = [], 0, 0
        end = time.time() + args.show_s
        settle = time.time() + 1.6  # let the camera and the 2-of-3 filter catch up with the new picture
        while time.time() < end:
            buf += ser.read(4096)
            root.update()
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode(errors="replace")
                m = LINE_RE.search(text)
                if m and time.time() > settle:
                    ps.append(float(m.group(1)))
                    confirmed += 1 if m.group(4) else 0
                pm = PERSON_RE.search(text)
                if pm and time.time() > settle and pm.group(3) == "PERSON":
                    persons += 1
        results.append({"label": "pothole" if is_pos else "no pothole", "name": name, "frames": len(ps),
                        "mean_p": float(np.mean(ps)) if ps else None, "max_p": float(max(ps)) if ps else None,
                        "frames_over_threshold": int(sum(p >= args.threshold for p in ps)), "confirmed_frames": confirmed})
        print(f"[{k + 1}/{len(order)}] {results[-1]['label']:11s} frames={len(ps)} mean p={results[-1]['mean_p']}")
    show_text("Done.")
    root.destroy()
    ser.close()

    def summary(label):
        rows = [r for r in results if r["label"] == label and r["frames"]]
        frames = sum(r["frames"] for r in rows)
        over = sum(r["frames_over_threshold"] for r in rows)
        conf = sum(r["confirmed_frames"] for r in rows)
        flagged = sum(1 for r in rows if r["confirmed_frames"] > 0)
        return {"images": len(rows), "frames": frames, "frames_over_threshold": over, "confirmed_frames": conf,
                "images_flagged_at_least_once": flagged,
                "mean_p": float(np.mean([r["mean_p"] for r in rows])) if rows else None}

    report = {"threshold": args.threshold, "pothole": summary("pothole"), "no_pothole": summary("no pothole"), "per_image": results}
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("threshold", "pothole", "no_pothole")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
