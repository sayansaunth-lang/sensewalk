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
        return self.label in HAZARD_RELEVANT_CLASSES or self.label in GROUND_HAZARD_CLASSES


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


# ---------------------------------------------------------------------------
# Custom ground-hazard model (potholes etc.) — trained by training/, run here.
# ---------------------------------------------------------------------------

HAZARD_ONNX_PATH = MODELS_DIR / "hazard_yolov8n_320.onnx"
HAZARD_CLASSES_PATH = MODELS_DIR / "hazard_classes.txt"

# Labels from the custom hazard model that mean "something on the ground ahead
# that you could fall into or trip over". Kept separate from
# HAZARD_RELEVANT_CLASSES (COCO objects like person/car) so one kind of
# detection can never hide the other in any_hazard_relevant().
GROUND_HAZARD_CLASSES = {"pothole", "stairs", "curb", "open_drain"}

HAZARD_DEFAULT_CONFIDENCE = 0.35
HAZARD_DEFAULT_NMS_IOU = 0.45

# A person whose bounding box is at least this fraction of the frame height is
# treated as "nearby". Vision has no true depth (that is the ToF/ultrasonic
# sensors' job — docs/ARCHITECTURE.md design rule #2), so apparent size is a
# deliberately crude proxy, not a distance measurement. Tune on real footage.
NEARBY_MIN_HEIGHT_FRACTION = 0.45


def letterbox(image, size: int, pad_value: int = 114):
    """Resize keeping aspect ratio and pad to a size x size square — the same
    preprocessing YOLO models are trained with. Returns
    (padded_image, scale, pad_x, pad_y) so boxes can be mapped back."""
    import cv2
    import numpy as np

    h, w = image.shape[:2]
    scale = min(size / h, size / w)
    new_w, new_h = int(round(w * scale)), int(round(h * scale))
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    pad_x, pad_y = (size - new_w) // 2, (size - new_h) // 2
    canvas = np.full((size, size, 3), pad_value, dtype=np.uint8)
    canvas[pad_y : pad_y + new_h, pad_x : pad_x + new_w] = resized
    return canvas, scale, pad_x, pad_y


def postprocess_yolo_output(
    output,
    class_names: Sequence[str],
    scale: float,
    pad_x: int,
    pad_y: int,
    orig_w: int,
    orig_h: int,
    confidence_threshold: float = HAZARD_DEFAULT_CONFIDENCE,
    nms_iou: float = HAZARD_DEFAULT_NMS_IOU,
) -> list[Detection]:
    """Decode a YOLOv8-style ONNX output tensor into Detections in original
    frame pixels. Accepts shape (1, 4+nc, N) (the standard export) or
    (1, N, 4+nc). Pure numpy + cv2.dnn.NMSBoxes — unit-testable with
    synthetic tensors, no model file needed."""
    import cv2
    import numpy as np

    out = np.asarray(output)
    if out.ndim == 3:
        out = out[0]
    channels = 4 + len(class_names)
    # Decide the layout from the known channel count rather than guessing from
    # which dimension is bigger. Channels-first (the standard export) wins a tie.
    if out.shape[0] == channels:
        out = out.T  # (4+nc, N) -> (N, 4+nc)
    elif out.shape[1] != channels:
        raise ValueError(
            f"model output shape {tuple(out.shape)} does not match {len(class_names)} class names "
            f"(expected a dimension of {channels} = 4 box values + one score per class)"
        )

    class_scores = out[:, 4:]
    class_ids = class_scores.argmax(axis=1)
    confidences = class_scores.max(axis=1)
    keep = confidences >= confidence_threshold
    if not keep.any():
        return []

    boxes_xywh, confidences, class_ids = out[keep, :4], confidences[keep], class_ids[keep]

    rects, scores = [], []
    for cx, cy, w, h in boxes_xywh:
        x1 = (cx - w / 2 - pad_x) / scale
        y1 = (cy - h / 2 - pad_y) / scale
        rects.append([float(x1), float(y1), float(w / scale), float(h / scale)])
    scores = [float(c) for c in confidences]

    indices = cv2.dnn.NMSBoxes(rects, scores, confidence_threshold, nms_iou)
    detections: list[Detection] = []
    for i in np.array(indices).flatten():
        x, y, w, h = rects[int(i)]
        x1, y1 = max(0, int(round(x))), max(0, int(round(y)))
        x2, y2 = min(orig_w, int(round(x + w))), min(orig_h, int(round(y + h)))
        if x2 <= x1 or y2 <= y1:
            continue
        detections.append(
            Detection(label=class_names[int(class_ids[int(i)])], confidence=scores[int(i)], box=(x1, y1, x2, y2))
        )
    detections.sort(key=lambda d: d.confidence, reverse=True)
    return detections


def load_class_names(path: Path = HAZARD_CLASSES_PATH) -> list[str]:
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


class YoloOnnxDetector:
    """The project's own trained ground-hazard detector (potholes, ...),
    exported by training/train_hazard_model.py to ONNX and run with OpenCV's
    DNN module — so it needs no runtime beyond opencv-python, which the Pi
    already has. Weights: vision/pi/models/hazard_yolov8n_320.onnx plus
    hazard_classes.txt (see training/README.md)."""

    def __init__(
        self,
        model_path: Path = HAZARD_ONNX_PATH,
        classes_path: Path = HAZARD_CLASSES_PATH,
        confidence_threshold: float = HAZARD_DEFAULT_CONFIDENCE,
        nms_iou: float = HAZARD_DEFAULT_NMS_IOU,
        input_size: int = 320,
    ) -> None:
        import cv2

        if not model_path.exists() or not classes_path.exists():
            raise FileNotFoundError(
                f"Hazard model not found at {model_path} / {classes_path}. "
                "Train it with training/train_hazard_model.py or copy a trained export into vision/pi/models/."
            )
        self._cv2 = cv2
        self._net = cv2.dnn.readNetFromONNX(str(model_path))
        self.class_names = load_class_names(classes_path)
        self.confidence_threshold = confidence_threshold
        self.nms_iou = nms_iou
        self.input_size = input_size

    def detect(self, frame) -> list[Detection]:
        cv2 = self._cv2
        h, w = frame.shape[:2]
        padded, scale, pad_x, pad_y = letterbox(frame, self.input_size)
        blob = cv2.dnn.blobFromImage(padded, 1 / 255.0, (self.input_size, self.input_size), swapRB=True, crop=False)
        self._net.setInput(blob)
        output = self._net.forward()
        return postprocess_yolo_output(
            output, self.class_names, scale, pad_x, pad_y, w, h, self.confidence_threshold, self.nms_iou
        )


def is_nearby(det: Detection, frame_height: int, min_fraction: float = NEARBY_MIN_HEIGHT_FRACTION) -> bool:
    """Crude 'close enough to matter' test from apparent size — see
    NEARBY_MIN_HEIGHT_FRACTION for why this is a proxy, not a measurement."""
    if frame_height <= 0:
        return False
    return (det.box[3] - det.box[1]) / frame_height >= min_fraction


def nearest_person(detections: list[Detection], frame_height: int) -> Optional[Detection]:
    """Largest-looking (closest) person, if any is 'nearby' by is_nearby()."""
    people = [d for d in detections if d.label == "person" and is_nearby(d, frame_height)]
    if not people:
        return None
    return max(people, key=lambda d: d.box[3] - d.box[1])


def find_ground_hazard(detections: list[Detection], min_confidence: float = HAZARD_DEFAULT_CONFIDENCE) -> Optional[Detection]:
    """Highest-confidence ground hazard (pothole/stairs/...), if any."""
    hits = [d for d in detections if d.label in GROUND_HAZARD_CLASSES and d.confidence >= min_confidence]
    if not hits:
        return None
    return max(hits, key=lambda d: d.confidence)


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
            from tflite_runtime.interpreter import Interpreter  # Raspberry Pi OS (piwheels)
        except ImportError:
            try:
                from ai_edge_litert.interpreter import Interpreter  # Windows/macOS/Linux dev machines
            except ImportError:
                from tensorflow.lite import Interpreter  # last resort: full tensorflow

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


class RollingConfirm:
    """Require a detection in at least `k` of the last `n` inference results
    before reporting it — the vision-side twin of the firmware's confirm-twice
    rule (B2 in the learning roadmap). One flickery frame should not flip the
    system into a warning state or make it speak."""

    def __init__(self, k: int = 2, n: int = 3) -> None:
        if not 1 <= k <= n:
            raise ValueError("need 1 <= k <= n")
        self.k, self.n = k, n
        self._history: list[bool] = []

    def observe(self, present: bool) -> bool:
        self._history.append(bool(present))
        if len(self._history) > self.n:
            self._history.pop(0)
        return sum(self._history) >= self.k
