"""MobileNet-SSD object detection (C3v in the learning roadmap).

Deliberately classification-only — depth/distance is owned by the ToF and
ultrasonic sensors on the ESP32 side (see docs/ARCHITECTURE.md design rule
#2). This module answers "what is in front of the user", never "how far".

Uses OpenCV's DNN module against the standard Caffe MobileNet-SSD model
(the widely-used 20-class VOC version) so no separate TFLite runtime
dependency is required on top of opencv-python.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
PROTOTXT_PATH = MODELS_DIR / "MobileNetSSD_deploy.prototxt"
CAFFEMODEL_PATH = MODELS_DIR / "MobileNetSSD_deploy.caffemodel"

# Standard 20-class + background label set for this Caffe MobileNet-SSD model.
VOC_CLASSES = [
    "background", "aeroplane", "bicycle", "bird", "boat", "bottle", "bus",
    "car", "cat", "chair", "cow", "diningtable", "dog", "horse",
    "motorbike", "person", "pottedplant", "sheep", "sofa", "train",
    "tvmonitor",
]

# Classes SENSEWALK actually cares about for the "person nearby" hazard
# escalation (fusion/state_machine.py) — everything else is still labelled
# in the demo/log output but does not drive fusion decisions.
HAZARD_RELEVANT_CLASSES = {"person", "bicycle", "car", "motorbike", "bus", "dog", "chair"}

DEFAULT_CONFIDENCE_THRESHOLD = 0.5
DEFAULT_INPUT_SIZE = (300, 300)  # native MobileNet-SSD input


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    box: tuple[int, int, int, int]  # (x1, y1, x2, y2) in original frame pixels

    @property
    def is_hazard_relevant(self) -> bool:
        return self.label in HAZARD_RELEVANT_CLASSES


class MobileNetSSDDetector:
    def __init__(
        self,
        prototxt_path: Path = PROTOTXT_PATH,
        caffemodel_path: Path = CAFFEMODEL_PATH,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        input_size: tuple[int, int] = DEFAULT_INPUT_SIZE,
    ) -> None:
        import cv2  # lazy import

        if not prototxt_path.exists() or not caffemodel_path.exists():
            raise FileNotFoundError(
                f"MobileNet-SSD model files not found at {prototxt_path} / {caffemodel_path}. "
                "Run vision/pi/models/download_models.sh first."
            )
        self._cv2 = cv2
        self._net = cv2.dnn.readNetFromCaffe(str(prototxt_path), str(caffemodel_path))
        self.confidence_threshold = confidence_threshold
        self.input_size = input_size

    def detect(self, frame) -> list[Detection]:
        cv2 = self._cv2
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(
            cv2.resize(frame, self.input_size), 0.007843, self.input_size, 127.5
        )
        self._net.setInput(blob)
        raw = self._net.forward()

        detections: list[Detection] = []
        for i in range(raw.shape[2]):
            confidence = float(raw[0, 0, i, 2])
            if confidence < self.confidence_threshold:
                continue
            class_id = int(raw[0, 0, i, 1])
            if class_id < 0 or class_id >= len(VOC_CLASSES):
                continue
            label = VOC_CLASSES[class_id]
            box = raw[0, 0, i, 3:7] * [w, h, w, h]
            x1, y1, x2, y2 = box.astype(int)
            detections.append(Detection(label=label, confidence=confidence, box=(x1, y1, x2, y2)))
        return detections

    @staticmethod
    def draw_detections(frame, detections: list[Detection]):
        import cv2

        for det in detections:
            x1, y1, x2, y2 = det.box
            color = (0, 0, 255) if det.is_hazard_relevant else (0, 255, 0)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label_text = f"{det.label}: {det.confidence:.2f}"
            cv2.putText(
                frame, label_text, (x1, max(15, y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2,
            )
        return frame


def any_hazard_relevant(detections: list[Detection]) -> Optional[Detection]:
    """Returns the highest-confidence hazard-relevant detection, if any —
    this is what feeds SensorSnapshot.vision_person_nearby in fusion."""
    relevant = [d for d in detections if d.is_hazard_relevant]
    if not relevant:
        return None
    return max(relevant, key=lambda d: d.confidence)
