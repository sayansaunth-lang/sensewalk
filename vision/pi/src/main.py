#!/usr/bin/env python3
"""Vision pipeline entry point — Phase 3 of the build plan.

Wires together: camera source -> MobileNet-SSD detection -> conditional
OCR -> fusion state machine -> speech alert -> haptic command back over
UART. Run with --preview on a dev machine with a display to see boxes/FPS
drawn live; run headless (default) on the Pi during real field tests.

    python3 vision/pi/src/main.py --camera picamera2 --serial-port /dev/serial0
    python3 vision/pi/src/main.py --camera opencv --camera-source 0 --preview   # dev machine, webcam
    python3 vision/pi/src/main.py --camera opencv --camera-source test/data/sample.mp4 --preview
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from comms.python.serial_link import SerialLink  # noqa: E402
from fusion.state_machine import SensorFusion, SensorSnapshot  # noqa: E402
from speech.tts import AlertSpeaker  # noqa: E402
from vision.pi.src.camera import FPSCounter, OpenCVCameraSource, Picamera2Source  # noqa: E402
from vision.pi.src.detector import MobileNetSSDDetector, any_hazard_relevant  # noqa: E402
from vision.pi.src.ocr import read_sign, should_attempt_ocr  # noqa: E402


def build_camera(args):
    if args.camera == "picamera2":
        return Picamera2Source(size=(args.width, args.height))
    return OpenCVCameraSource(args.camera_source, size=(args.width, args.height))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--camera", choices=["picamera2", "opencv"], default="opencv")
    parser.add_argument("--camera-source", default=0, help="OpenCV backend only: device index or file path")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--serial-port", default=None, help="e.g. /dev/serial0 — omit to run vision-only, no UART")
    parser.add_argument("--preview", action="store_true", help="show an on-screen window with boxes + FPS")
    parser.add_argument("--no-ocr", action="store_true", help="disable OCR even when a sign-like region is seen")
    parser.add_argument("--no-speech", action="store_true", help="disable TTS output (useful for headless dev runs)")
    args = parser.parse_args()

    try:
        args.camera_source = int(args.camera_source)
    except (TypeError, ValueError):
        pass  # a file path, leave as string

    camera = build_camera(args)
    detector = MobileNetSSDDetector()
    fusion = SensorFusion()
    speaker = None if args.no_speech else AlertSpeaker()
    fps_counter = FPSCounter()

    link = None
    snapshot = SensorSnapshot()
    if args.serial_port:
        link = SerialLink(args.serial_port)
        link.on_message("tof_fwd", lambda m: setattr(snapshot, "tof_fwd_mm", m.int_value()))
        link.on_message("tof_gnd", lambda m: setattr(snapshot, "tof_gnd_mm", m.int_value()))
        link.on_message("us_l", lambda m: setattr(snapshot, "us_l_cm", m.int_value()))
        link.on_message("us_c", lambda m: setattr(snapshot, "us_c_cm", m.int_value()))
        link.on_message("us_r", lambda m: setattr(snapshot, "us_r_cm", m.int_value()))
        link.on_message("fall", lambda m: setattr(snapshot, "fall_flag", bool(m.int_value())))

        def on_grip(m):
            mask = m.int_value()
            snapshot.grip_left = bool(mask & 0b01)
            snapshot.grip_right = bool(mask & 0b10)
            snapshot.last_grip_at = time.monotonic()

        link.on_message("grip", on_grip)
        link.open()

    print("SENSEWALK vision pipeline running. Ctrl+C to stop.")
    try:
        for frame in camera.frames():
            if link is not None:
                link.poll()
                snapshot.mcu_alive = link.stats.mcu_alive

            detections = detector.detect(frame)
            hazard_det = any_hazard_relevant(detections)
            snapshot.vision_person_nearby = hazard_det is not None and hazard_det.label == "person"

            snapshot.ocr_text = None
            if not args.no_ocr and should_attempt_ocr(frame):
                try:
                    result = read_sign(frame)
                    if result.text and result.mean_confidence > 40:
                        snapshot.ocr_text = result.text
                except RuntimeError:
                    pass  # tesseract not installed on this machine — skip silently

            decision = fusion.update(snapshot)
            fps = fps_counter.tick()

            if decision.alert_phrase_key and speaker is not None:
                speaker.speak(decision.alert_phrase_key)

            if link is not None:
                left = 200 if snapshot.vision_person_nearby else 0
                right = left
                link.send("haptic", f"{left}|{right}")

            if args.preview:
                import cv2

                MobileNetSSDDetector.draw_detections(frame, detections)
                cv2.putText(
                    frame, f"FPS: {fps:.1f}  state: {decision.state.name}",
                    (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2,
                )
                cv2.imshow("SENSEWALK", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        camera.close()
        if link is not None:
            link.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
