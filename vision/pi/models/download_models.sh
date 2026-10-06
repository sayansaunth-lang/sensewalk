#!/usr/bin/env bash
# The Caffe MobileNet-SSD backend (--detector-backend opencv-dnn) is NOT
# supported out of the box.
#
# The weights this script used to fetch could not be verified: the file name
# it pointed to is the unmerged training snapshot, which does not match
# deploy.prototxt (that needs the batch-norm-merged MobileNetSSD_deploy.caffemodel),
# and no trustworthy download location for the merged file was found.
#
# Use the default TFLite backend instead — it is tested end-to-end against real
# weights and is lighter on a Raspberry Pi 3B anyway:
#
#     bash vision/pi/models/download_tflite_model.sh
#
# If you obtain a verified MobileNetSSD_deploy.caffemodel + prototxt yourself,
# place them in this directory and run main.py with --detector-backend opencv-dnn.
echo "This backend has no verified weight source. Run download_tflite_model.sh instead." >&2
exit 1
