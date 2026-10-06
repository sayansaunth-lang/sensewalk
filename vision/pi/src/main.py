#!/usr/bin/env python3
"""Vision pipeline entry point — Phase 3 of the build plan.

Wires together: camera source -> MobileNet-SSD detection -> conditional
OCR -> fusion state machine -> speech alert -> haptic command back over
UART. Run with --preview on a dev machine with a display to see boxes/FPS
drawn live; run headless (default) on the Pi during real field tests.

    python3 vision/pi/src/main.py --camera picamera2 --serial-port /dev/serial0
    python3 vision/pi/src/main.py --camera opencv --camera-source 0 --preview   # dev machine, webcam
    python3 vision/pi/src/main.py --camera opencv --camera-source test/data/sample.mp4 --preview

Before the ESP32 side exists or is wired up, run with --sim to drive the
fusion/speech/haptics path off a scripted synthetic sensor feed
(comms/python/sim_feed.py) instead of real UART — the vision detection
itself still runs against a real camera/webcam/video file, only the
ESP32-side telemetry (ToF/ultrasonic/IMU/grip) is faked:

    python3 vision/pi/src/main.py --camera opencv --camera-source 0 --sim --preview

On constrained hardware (e.g. a Raspberry Pi 3B with 1GB RAM instead of a
Pi 4 — see docs/PI3B_LOW_RAM_SETUP.md), two flags matter most:

    --detector-backend tflite       # the default; quantized MobileNet-SSD, lightest option
    --process-every-n-frames 3      # only run detection on every 3rd frame; camera still streams live
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from comms.python.serial_link import SerialLink  # noqa: E402
from emergency.notifier import numbers_from_env  # noqa: E402
from fusion.state_machine import SensorFusion, SensorSnapshot  # noqa: E402
from speech.tts import AlertSpeaker  # noqa: E402
from vision.pi.src.camera import FPSCounter, OpenCVCameraSource, Picamera2Source  # noqa: E402
from vision.pi.src.detector import (  # noqa: E402
    MobileNetSSDDetector,
    RollingConfirm,
    TFLiteSSDDetector,
    YoloOnnxDetector,
    draw_detections,
    find_ground_hazard,
    nearest_person,
)
from vision.pi.src.ocr import read_sign, should_attempt_ocr  # noqa: E402


def build_camera(args):
    if args.camera == "picamera2":
        return Picamera2Source(size=(args.width, args.height))
    return OpenCVCameraSource(args.camera_source, size=(args.width, args.height))


def build_detector(args):
    if args.detector_backend == "tflite":
        return TFLiteSSDDetector()
    return MobileNetSSDDetector()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--camera", choices=["picamera2", "opencv"], default="opencv")
    parser.add_argument("--camera-source", default=0, help="OpenCV backend only: device index, file path, or stream URL")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument(
        "--detector-backend",
        choices=["opencv-dnn", "tflite"],
        default="tflite",
        help="tflite (default: tested end-to-end and lightest — see docs/PI3B_LOW_RAM_SETUP.md) or "
        "opencv-dnn (requires Caffe weights you supply yourself; see models/download_models.sh)",
    )
    parser.add_argument(
        "--hazard-model",
        nargs="?",
        const="default",
        default=None,
        metavar="PATH.onnx",
        help="also run the project's own trained ground-hazard detector (potholes etc., see training/). "
        "Bare flag uses vision/pi/models/hazard_yolov8n_320.onnx. Costs extra CPU per inference — "
        "raise --process-every-n-frames on a Pi 3B.",
    )
    parser.add_argument(
        "--process-every-n-frames",
        type=int,
        default=1,
        help="only run detection/OCR on every Nth frame (default 1 = every frame); "
        "raise this on slower hardware — the camera still streams at full rate, "
        "only the expensive inference calls are skipped",
    )
    parser.add_argument("--serial-port", default=None, help="e.g. /dev/serial0 — omit to run vision-only, no UART")
    parser.add_argument("--preview", action="store_true", help="show an on-screen window with boxes + FPS")
    parser.add_argument("--no-ocr", action="store_true", help="disable OCR even when a sign-like region is seen")
    parser.add_argument("--no-speech", action="store_true", help="disable TTS output (useful for headless dev runs)")
    parser.add_argument(
        "--sim",
        action="store_true",
        help="drive ESP32-side telemetry from a scripted synthetic feed instead of real UART "
        "(comms/python/sim_feed.py) — for developing/demoing before hardware is wired up",
    )
    parser.add_argument("--gsm-port", default=None, help="SIM800L serial port (e.g. /dev/ttyUSB1). Enables fall -> SMS alerts")
    parser.add_argument("--gsm-baud", type=int, default=9600)
    parser.add_argument("--gps-port", default=None, help="NEO-6M serial port (e.g. /dev/ttyUSB0); adds a map link to the SMS")
    parser.add_argument("--gps-baud", type=int, default=9600)
    parser.add_argument(
        "--emergency-number", action="append", default=[], metavar="+91XXXXXXXXXX",
        help="who to text on a confirmed fall (repeatable). Falls back to the "
        "SENSEWALK_EMERGENCY_NUMBERS environment variable, so numbers never need to live in code",
    )
    parser.add_argument(
        "--fall-confirm-s", type=float, default=10.0,
        help="seconds the user has to grip the handle to cancel a detected fall before the SMS is sent",
    )
    args = parser.parse_args()

    if args.sim and args.serial_port:
        parser.error("--sim and --serial-port are mutually exclusive")
    if args.process_every_n_frames < 1:
        parser.error("--process-every-n-frames must be >= 1")

    try:
        args.camera_source = int(args.camera_source)
    except (TypeError, ValueError):
        pass  # a file path or stream URL, leave as string

    camera = build_camera(args)
    detector = build_detector(args)
    hazard_detector = None
    if args.hazard_model:
        if args.hazard_model == "default":
            hazard_detector = YoloOnnxDetector()
        else:
            hazard_detector = YoloOnnxDetector(model_path=Path(args.hazard_model))
    person_confirm, ground_confirm = RollingConfirm(2, 3), RollingConfirm(2, 3)
    fusion = SensorFusion()
    speaker = None if args.no_speech else AlertSpeaker()
    fps_counter = FPSCounter()

    coordinator = None
    if args.gsm_port:
        import serial

        from emergency.coordinator import EmergencyCoordinator
        from emergency.nmea import GpsReader
        from emergency.notifier import EmergencyNotifier
        from emergency.sim800 import Sim800

        numbers = args.emergency_number or numbers_from_env()
        if not numbers:
            parser.error("--gsm-port needs at least one --emergency-number (or SENSEWALK_EMERGENCY_NUMBERS)")
        gps_reader = None
        if args.gps_port:
            import threading

            gps_reader = GpsReader()
            threading.Thread(
                target=gps_reader.run,
                args=(serial.Serial(args.gps_port, args.gps_baud, timeout=0.5), threading.Event()),
                daemon=True,
            ).start()
        gsm = Sim800(serial.Serial(args.gsm_port, args.gsm_baud, timeout=0.2))
        coordinator = EmergencyCoordinator(EmergencyNotifier(gsm, gps_reader, numbers), args.fall_confirm_s)
        print(f"Emergency alerts ON: {len(numbers)} recipient(s), {args.fall_confirm_s:.0f}s cancel window, "
              f"GPS {'on' if gps_reader else 'off'}")

    link = None
    sim_feed = None
    snapshot = SensorSnapshot()
    if args.sim:
        from comms.python.sim_feed import SimulatedFeed

        sim_feed = SimulatedFeed()
        snapshot = sim_feed.tick()
        print("Running with --sim: ESP32 telemetry is scripted, not real (see comms/python/sim_feed.py)")
    if args.serial_port:
        link = SerialLink(args.serial_port)
        link.on_message("tof_fwd", lambda m: setattr(snapshot, "tof_fwd_mm", m.int_value()))
        link.on_message("tof_gnd", lambda m: setattr(snapshot, "tof_gnd_mm", m.int_value()))
        link.on_message("us_l", lambda m: setattr(snapshot, "us_l_cm", m.int_value()))
        link.on_message("us_c", lambda m: setattr(snapshot, "us_c_cm", m.int_value()))
        link.on_message("us_r", lambda m: setattr(snapshot, "us_r_cm", m.int_value()))
        link.on_message("fall", lambda m: coordinator.report_fall() if (coordinator and m.int_value()) else None)

        def on_grip(m):
            mask = m.int_value()
            snapshot.grip_left = bool(mask & 0b01)
            snapshot.grip_right = bool(mask & 0b10)
            snapshot.last_grip_at = time.monotonic()

        link.on_message("grip", on_grip)
        link.open()

    print(f"SENSEWALK vision pipeline running (backend={args.detector_backend}, "
          f"every {args.process_every_n_frames} frame(s)). Ctrl+C to stop.")
    frame_index = 0
    detections: list = []
    # Vision results persist between inference frames. Re-applying them every frame
    # matters when --process-every-n-frames > 1 or --sim rebuilds the snapshot each tick.
    vision_person, vision_ground, ocr_last = False, None, None
    try:
        for frame in camera.frames():
            if sim_feed is not None:
                snapshot = sim_feed.tick()
                snapshot.mcu_alive = True
            elif link is not None:
                link.poll()
                snapshot.mcu_alive = link.stats.mcu_alive
                if coordinator is not None:
                    # The ESP32 only ever sends fall,1; the latch turns that into a flag that clears.
                    snapshot.fall_flag = coordinator.fall_active

            run_inference = (frame_index % args.process_every_n_frames) == 0
            frame_index += 1

            if run_inference:
                detections = detector.detect(frame)
                frame_h = frame.shape[0]
                # "nearby" = apparent size, a crude proxy (see detector.NEARBY_MIN_HEIGHT_FRACTION);
                # real distance comes from the ESP32's ToF/ultrasonic sensors.
                vision_person = person_confirm.observe(nearest_person(detections, frame_h) is not None)
                if hazard_detector is not None:
                    hazard_dets = hazard_detector.detect(frame)
                    ground = find_ground_hazard(hazard_dets)
                    confirmed = ground_confirm.observe(ground is not None)
                    vision_ground = ground.label if (ground and confirmed) else None
                    detections = detections + hazard_dets

                ocr_last = None
                if not args.no_ocr and should_attempt_ocr(frame):
                    try:
                        result = read_sign(frame)
                        if result.text and result.mean_confidence > 40:
                            ocr_last = result.text
                    except RuntimeError as exc:
                        print(f"[ocr] disabled for this run: {exc}")
                        args.no_ocr = True  # don't pay the preprocessing cost on every frame

            snapshot.vision_person_nearby = vision_person
            snapshot.vision_ground_hazard = vision_ground
            snapshot.ocr_text = ocr_last

            decision = fusion.update(snapshot)
            fps = fps_counter.tick()

            if coordinator is not None:
                coordinator.update(grip_present=snapshot.grip_left or snapshot.grip_right)
                for event in coordinator.pop_events():
                    print(f"[emergency] {event}")
                    key = {"countdown": "fall_countdown", "sent": "alert_sent", "failed": "alert_failed"}[event]
                    if speaker is not None:
                        speaker.speak(key, min_repeat_interval_s=0)

            key = decision.alert_phrase_key
            if key == "fall_alert" and coordinator is not None:
                key = None  # the countdown/sent/failed phrases above replace the premature "sending alert"
            if key and speaker is not None:
                # sign_read's template needs the recognised text; every other phrase ignores it
                speaker.speak(key, text=snapshot.ocr_text or "")

            if link is not None:
                left = 200 if (snapshot.vision_person_nearby or snapshot.vision_ground_hazard) else 0
                right = left
                link.send("haptic", f"{left}|{right}")

            if args.preview:
                import cv2

                draw_detections(frame, detections)
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
