"""Tesseract OCR for sign/label reading (C4v in the learning roadmap).

Deliberately separable from the safety-critical detection pipeline both in
code and in call order: OCR is expensive, so callers should only invoke
read_sign() when a sign-like region has already been located (e.g. a large
enough rectangular contour), not on every frame — see
should_attempt_ocr().
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class OcrResult:
    text: str
    mean_confidence: float  # 0-100, Tesseract's own per-word confidence averaged


def preprocess_for_ocr(frame):
    """Grayscale -> threshold -> (light) deskew. Raw camera frames handed
    directly to Tesseract perform poorly (C4v) — this is the minimum viable
    cleanup before OCR, not a full document-scanner pipeline."""
    import cv2
    import numpy as np

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    # Otsu thresholding adapts to lighting instead of a fixed cutoff, which
    # C4v's own test plan documents as failing hard under uneven lighting.
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    coords = cv2.findNonZero(255 - thresh)
    if coords is not None:
        angle = cv2.minAreaRect(coords)[-1]
        # cv2.minAreaRect returns an angle in (-90, 0]; normalize toward the
        # nearest axis so small skew is corrected without over-rotating text
        # that's already close to upright.
        if angle < -45:
            angle = 90 + angle
        if abs(angle) > 0.5:
            (h, w) = thresh.shape[:2]
            center = (w // 2, h // 2)
            m = cv2.getRotationMatrix2D(center, angle, 1.0)
            thresh = cv2.warpAffine(
                thresh, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
            )
    return thresh


def find_sign_like_regions(frame, min_area_fraction: float = 0.02) -> list[tuple[int, int, int, int]]:
    """Locate roughly-rectangular, high-contrast regions that might be a
    sign or label — used as the OCR trigger condition so Tesseract doesn't
    run on every frame (C4v: 'running OCR on every frame will wreck your
    FPS'). Returns (x, y, w, h) boxes in frame pixel coordinates."""
    import cv2

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    frame_area = frame.shape[0] * frame.shape[1]
    min_area = frame_area * min_area_fraction
    regions = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if area < min_area:
            continue
        aspect = w / max(h, 1)
        if 1.2 <= aspect <= 8.0:  # signs are usually wider than tall, not square/extreme
            regions.append((x, y, w, h))
    return regions


def should_attempt_ocr(frame) -> bool:
    return len(find_sign_like_regions(frame)) > 0


def read_sign(frame, roi: Optional[tuple[int, int, int, int]] = None) -> OcrResult:
    """Run Tesseract on `frame` (or a cropped region of interest if given).
    Raises RuntimeError if pytesseract/tesseract-ocr isn't installed —
    callers on a dev machine without the tesseract binary should catch this
    and fall back to skipping the OCR feature."""
    import pytesseract

    image = frame
    if roi is not None:
        x, y, w, h = roi
        image = frame[y : y + h, x : x + w]

    processed = preprocess_for_ocr(image)

    data = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT)
    words = []
    confidences = []
    for text, conf in zip(data["text"], data["conf"]):
        text = text.strip()
        conf_val = float(conf)
        if text and conf_val >= 0:
            words.append(text)
            confidences.append(conf_val)

    joined = " ".join(words)
    mean_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return OcrResult(text=joined, mean_confidence=mean_conf)
