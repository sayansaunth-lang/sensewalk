#!/usr/bin/env bash
# Downloads the pretrained quantized MobileNet-SSD v1 (COCO, 90-class) TFLite
# model used by vision/pi/src/detector.py's TFLiteSSDDetector — the default,
# verified backend, and the lightest option for a Raspberry Pi 3B (1GB).
#
# This is Google's own official TFLite object-detection example model, served
# from Google's storage bucket. The zip's SHA-256 is pinned below: large
# downloads have been seen to arrive silently corrupted on some networks, and
# a truncated model file fails in confusing ways far from the cause.
set -euo pipefail
cd "$(dirname "$0")"

MODEL_ZIP_URL="https://storage.googleapis.com/download.tensorflow.org/models/tflite/coco_ssd_mobilenet_v1_1.0_quant_2018_06_29.zip"
EXPECTED_SHA256="a809cd290b4d6a2e8a9d5dad076e0bd695b8091974e0eed1052b480b2f21b6dc"

echo "Downloading quantized SSD MobileNet v1 (COCO)..."
curl -fL --retry 5 -C - "$MODEL_ZIP_URL" -o _ssd_mobilenet_v1_coco_quant.zip

actual="$(sha256sum _ssd_mobilenet_v1_coco_quant.zip | cut -d' ' -f1)"
if [ "$actual" != "$EXPECTED_SHA256" ]; then
  echo "ERROR: checksum mismatch (got $actual). The download is corrupt — delete it and retry." >&2
  rm -f _ssd_mobilenet_v1_coco_quant.zip
  exit 1
fi

echo "Checksum OK. Extracting..."
unzip -o _ssd_mobilenet_v1_coco_quant.zip -d _tmp_extract
mv _tmp_extract/detect.tflite ssd_mobilenet_v1_coco_quant.tflite
mv _tmp_extract/labelmap.txt coco_labelmap.txt
rm -rf _tmp_extract _ssd_mobilenet_v1_coco_quant.zip

echo "Done: ssd_mobilenet_v1_coco_quant.tflite + coco_labelmap.txt"
echo "Verify with: python3 -c \"from vision.pi.src.detector import TFLiteSSDDetector; TFLiteSSDDetector()\""
