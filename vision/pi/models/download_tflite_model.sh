#!/usr/bin/env bash
# Downloads the pretrained quantized MobileNet-SSD v1 (COCO, 90-class)
# TFLite model used by vision/pi/src/detector.py's TFLiteSSDDetector —
# the lighter-weight backend recommended for constrained hardware like a
# Raspberry Pi 3B with 1GB RAM (see docs/PI3B_LOW_RAM_SETUP.md).
#
# This is Google's own official TFLite object-detection example model
# (same one used in the TensorFlow Lite Raspberry Pi sample apps), served
# from Google's storage bucket.
set -euo pipefail
cd "$(dirname "$0")"

MODEL_ZIP_URL="https://storage.googleapis.com/download.tensorflow.org/models/tflite/coco_ssd_mobilenet_v1_1.0_quant_2018_06_29.zip"

echo "Downloading quantized SSD MobileNet v1 (COCO)..."
curl -fL "$MODEL_ZIP_URL" -o _ssd_mobilenet_v1_coco_quant.zip

echo "Extracting..."
unzip -o _ssd_mobilenet_v1_coco_quant.zip -d _tmp_extract

mv _tmp_extract/detect.tflite ssd_mobilenet_v1_coco_quant.tflite
mv _tmp_extract/labelmap.txt coco_labelmap.txt

rm -rf _tmp_extract _ssd_mobilenet_v1_coco_quant.zip

echo "Done: ssd_mobilenet_v1_coco_quant.tflite + coco_labelmap.txt"
echo "Verify with: python3 -c \"from vision.pi.src.detector import TFLiteSSDDetector; TFLiteSSDDetector()\""
