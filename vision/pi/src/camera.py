"""Camera source abstraction (C1v in the learning roadmap).

Two backends behind one interface so the same detector/OCR code runs on
the actual Pi Camera v3 (via picamera2/libcamera) and on a dev machine
webcam or video file (via OpenCV) for offline development:

    Picamera2Source   — real hardware, Raspberry Pi OS only
    OpenCVCameraSource — USB webcam or video file, for dev-machine testing

Both yield BGR numpy frames (OpenCV's native order) so downstream code
never needs to know which backend produced a frame.
"""
from __future__ import annotations

import time
from typing import Iterator, Optional, Protocol


class FrameSource(Protocol):
    def frames(self) -> Iterator["np.ndarray"]:  # noqa: F821 - numpy typed lazily
        ...

    def close(self) -> None:
        ...


class Picamera2Source:
    """Wraps picamera2 for the Pi Camera v3. Only usable on Raspberry Pi OS
    with libcamera + picamera2 installed (see vision/pi/requirements.txt note)."""

    def __init__(self, size: tuple[int, int] = (640, 480), fps: int = 30) -> None:
        from picamera2 import Picamera2  # lazy import — hardware-only dependency

        self._picam2 = Picamera2()
        config = self._picam2.create_video_configuration(
            main={"size": size, "format": "RGB888"},
            controls={"FrameRate": fps},
        )
        self._picam2.configure(config)
        self._picam2.start()
        time.sleep(1.0)  # sensor warm-up, avoids a garbage first frame

    def frames(self):
        import cv2  # lazy import

        while True:
            rgb = self._picam2.capture_array()
            yield cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    def close(self) -> None:
        self._picam2.stop()


class OpenCVCameraSource:
    """USB webcam (device index) or a video file path — used for dev-machine
    testing and for replaying recorded test clips (see test/README.md)."""

    def __init__(self, source: int | str = 0, size: Optional[tuple[int, int]] = None) -> None:
        import cv2  # lazy import

        self._cv2 = cv2
        self._cap = cv2.VideoCapture(source)
        if not self._cap.isOpened():
            raise RuntimeError(f"could not open camera/video source: {source!r}")
        if size is not None:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])

    def frames(self):
        while True:
            ok, frame = self._cap.read()
            if not ok:
                return
            yield frame

    def close(self) -> None:
        self._cap.release()


class FPSCounter:
    """Rolling frames-per-second measurement (C2v deliverable: prove the
    12-15 FPS target with a real, on-screen, logged number — not an assumed
    one)."""

    def __init__(self, window: int = 30) -> None:
        self.window = window
        self._timestamps: list[float] = []

    def tick(self) -> float:
        now = time.monotonic()
        self._timestamps.append(now)
        if len(self._timestamps) > self.window:
            self._timestamps.pop(0)
        if len(self._timestamps) < 2:
            return 0.0
        elapsed = self._timestamps[-1] - self._timestamps[0]
        if elapsed <= 0:
            return 0.0
        return (len(self._timestamps) - 1) / elapsed
