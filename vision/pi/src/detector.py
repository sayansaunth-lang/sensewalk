"""MobileNet-SSD object detection (C3v in the learning roadmap).

Deliberately classification-only — depth/distance is owned by the ToF and
ultrasonic sensors on the ESP32 side (see docs/ARCHITECTURE.md design rule
#2). This module answers "what is in front of the user", never "how far".

Two interchangeable backends, same Detection output shape:

- MobileNetSSDDetector: OpenCV's DNN module against the standard Caffe
  MobileNet-SSD (20-class VOC). Simplest setup — no extra runtime beyond
  opencv-python. This is the default.
- TFLiteSSDDetector: a quantized MobileNet-SSD (COCO) via the TFLite
  runtime. Meaningfully lighter on CPU/RAM than OpenCV's DNN module for
  the same architecture — worth switching to on constrained hardware like
  a Raspberry Pi 3B with 1GB RAM (see docs/PI3B_LOW_RAM_SETUP.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
PROTOTXT_PATH = MODELS_DIR / "MobileNetSSD_deploy.prototxt"
CAFFEMODEL_PATH = MODELS_DIR / "MobileNetSSD_deploy.caffemodel"
TFLITE_MODEL_PATH = MODELS_DIR / "ssd_mobilenet_v1_coco_quant.tflite"
TFLITE_LABELMAP_PATH = MODELS_DIR / "coco_labelmap.txt"

# Standard 20-class + background label set for this Caffe MobileNet-SSD model.
VOC_CLASSES = [
    "background", "aeroplane", "bicycle", "bird", "boat", "bottle", "bus",
    "car", "cat", "chair", "cow", "diningtable", "dog", "horse",
    "motorbike", "person", "pottedplant", "sheep", "sofa", "train",
    "tvmonitor",
]

# Classes SENSEWALK actually cares about for the "person nearby" hazard
# escalation (fusion/state_machine.py) — everything else is still labelled
# in the demo/log output but does not drive fusion decisions. Includes both
# "motorbike" (VOC/Caffe backend naming) and "motorcycle" (COCO/TFLite
# backend naming) since either detector may be active.
HAZARD_RELEVANT_CLASSES = {
    "person", "bicycle", "car", "motorbike", "motorcycle", "bus", "dog", "chair",
}

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


draw_detections = MobileNetSSDDetector.draw_detections  # backend-agnostic alias — operates only on Detection objects


def any_hazard_relevant(detections: list[Detection]) -> Optional[Detection]:
    """Returns the highest-confidence hazard-relevant detection, if any —
    this is what feeds SensorSnapshot.vision_person_nearby in fusion."""
    relevant = [d for d in detections if d.is_hazard_relevant]
    if not relevant:
        return None
    return max(relevant, key=lambda d: d.confidence)


def load_tflite_labels(labelmap_path: Path = TFLITE_LABELMAP_PATH) -> list[str]:
    """Loads a labelmap.txt (one label per line).

    GOTCHA (S3 in the learning roadmap — read this before debugging wrong
    labels): the standard pretrained quantized COCO SSD model's own output
    class indices are already 0-indexed with NO background class (index 0
    is "person", not a placeholder) — but the labelmap.txt file shipped
    alongside it conventionally starts with a "???" placeholder line to
    keep the FILE's line numbers matching the *original* 1-indexed COCO
    category ids. Loaded naively, that placeholder line shifts every label
    off by one against the model's actual output indices. This loader
    drops a leading "???" (or "background") line if present so `labels[i]`
    always matches what the model actually outputs for class index i.
    """
    with open(labelmap_path) as f:
        labels = [line.strip() for line in f.readlines()]
    if labels and labels[0].lower() in ("???", "background", "unlabeled"):
        labels = labels[1:]
    return labels


def postprocess_tflite_detections(
    boxes: Sequence[Sequence[float]],
    class_ids: Sequence[float],
    scores: Sequence[float],
    num_detections: int,
    labels: Sequence[str],
    frame_width: int,
    frame_height: int,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> list[Detection]:
    """Pure conversion from the TFLite "Detection PostProcess" op's four
    output tensors (locations, classes, scores, count) into Detection
    objects in the same (x1, y1, x2, y2) pixel-coordinate shape
    MobileNetSSDDetector.detect() produces — kept separate from
    TFLiteSSDDetector so it's unit-testable with plain lists, no tflite
    runtime or model file required.
    """
    detections: list[Detection] = []
    for i in range(int(num_detections)):
        score = float(scores[i])
        if score < confidence_threshold:
            continue
        class_id = int(class_ids[i])
        if class_id < 0 or class_id >= len(labels):
            continue
        label = labels[class_id]
        ymin, xmin, ymax, xmax = boxes[i]
        x1 = int(xmin * frame_width)
        y1 = int(ymin * frame_height)
        x2 = int(xmax * frame_width)
        y2 = int(ymax * frame_height)
        detections.append(Detection(label=label, confidence=score, box=(x1, y1, x2, y2)))
    return detections


class TFLiteSSDDetector:
    """Quantized MobileNet-SSD (COCO) via the TFLite runtime — see the
    module docstring for why you'd pick this over MobileNetSSDDetector on
    constrained hardware. Setup: run
    vision/pi/models/download_tflite_model.sh once, and
    `pip install tflite-runtime` (or plain `tensorflow`, which also ships
    a compatible tf.lite.Interpreter, as a fallback if a prebuilt
    tflite-runtime wheel isn't available for your Pi's OS/Python combo).
    """

    def __init__(
        self,
        model_path: Path = TFLITE_MODEL_PATH,
        labelmap_path: Path = TFLITE_LABELMAP_PATH,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> None:
        if not model_path.exists() or not labelmap_path.exists():
            raise FileNotFoundError(
                f"TFLite model files not found at {model_path} / {labelmap_path}. "
                "Run vision/pi/models/download_tflite_model.sh first."
            )

        try:
            from tflite_runtime.interpreter import Interpreter  # lazy import
        except ImportError:
            from tensorflow.lite import Interpreter  # fallback if only full tensorflow is installed

        self._interpreter = Interpreter(model_path=str(model_path))
        self._interpreter.allocate_tensors()
        self._input_details = self._interpreter.get_input_details()
        self._output_details = self._interpreter.get_output_details()

        input_shape = self._input_details[0]["shape"]  # [1, height, width, 3]
        self.input_size = (int(input_shape[2]), int(input_shape[1]))  # (width, height)
        self._input_is_float = self._input_details[0]["dtype"].__name__ == "float32"

        self.labels = load_tflite_labels(labelmap_path)
        self.confidence_threshold = confidence_threshold

    def detect(self, frame) -> list[Detection]:
        import cv2  # lazy import
        import numpy as np

        resized = cv2.resize(frame, self.input_size)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        input_data = np.expand_dims(rgb, axis=0)
        if self._input_is_float:
            input_data = (np.float32(input_data) - 127.5) / 127.5
        else:
            input_data = input_data.astype(np.uint8)

        self._interpreter.set_tensor(self._input_details[0]["index"], input_data)
        self._interpreter.invoke()

        # Standard "TFLite Detection PostProcess" op output order.
        boxes = self._interpreter.get_tensor(self._output_details[0]["index"])[0]
        class_ids = self._interpreter.get_tensor(self._output_details[1]["index"])[0]
        scores = self._interpreter.get_tensor(self._output_details[2]["index"])[0]
        num_detections = self._interpreter.get_tensor(self._output_details[3]["index"])[0]

        h, w = frame.shape[:2]
        return postprocess_tflite_detections(
            boxes, class_ids, scores, num_detections, self.labels, w, h, self.confidence_threshold
        )
