from vision.pi.src.detector import (
    Detection,
    any_hazard_relevant,
    load_tflite_labels,
    postprocess_tflite_detections,
)


def test_hazard_relevant_property():
    person = Detection(label="person", confidence=0.9, box=(0, 0, 10, 10))
    bottle = Detection(label="bottle", confidence=0.9, box=(0, 0, 10, 10))
    assert person.is_hazard_relevant is True
    assert bottle.is_hazard_relevant is False


def test_any_hazard_relevant_picks_highest_confidence():
    dets = [
        Detection(label="bottle", confidence=0.95, box=(0, 0, 1, 1)),
        Detection(label="person", confidence=0.6, box=(0, 0, 1, 1)),
        Detection(label="car", confidence=0.8, box=(0, 0, 1, 1)),
    ]
    best = any_hazard_relevant(dets)
    assert best is not None
    assert best.label == "car"


def test_any_hazard_relevant_returns_none_when_no_relevant_class():
    dets = [Detection(label="bottle", confidence=0.99, box=(0, 0, 1, 1))]
    assert any_hazard_relevant(dets) is None


def test_any_hazard_relevant_empty_list():
    assert any_hazard_relevant([]) is None


def test_motorcycle_spelling_is_hazard_relevant_too():
    # COCO/TFLite backend says "motorcycle"; VOC/Caffe backend says "motorbike".
    assert Detection(label="motorcycle", confidence=0.9, box=(0, 0, 1, 1)).is_hazard_relevant


def test_postprocess_tflite_detections_basic():
    labels = ["person", "bicycle", "car"]
    boxes = [[0.1, 0.2, 0.5, 0.6]]  # ymin, xmin, ymax, xmax
    class_ids = [0.0]
    scores = [0.87]

    detections = postprocess_tflite_detections(
        boxes, class_ids, scores, num_detections=1, labels=labels,
        frame_width=100, frame_height=200, confidence_threshold=0.5,
    )

    assert len(detections) == 1
    det = detections[0]
    assert det.label == "person"
    assert det.confidence == 0.87
    # xmin*100=20, ymin*200=20, xmax*100=60, ymax*200=100
    assert det.box == (20, 20, 60, 100)


def test_postprocess_tflite_detections_filters_below_threshold():
    detections = postprocess_tflite_detections(
        boxes=[[0, 0, 1, 1]], class_ids=[0], scores=[0.2], num_detections=1,
        labels=["person"], frame_width=10, frame_height=10, confidence_threshold=0.5,
    )
    assert detections == []


def test_postprocess_tflite_detections_ignores_out_of_range_class_id():
    detections = postprocess_tflite_detections(
        boxes=[[0, 0, 1, 1]], class_ids=[99], scores=[0.9], num_detections=1,
        labels=["person"], frame_width=10, frame_height=10, confidence_threshold=0.5,
    )
    assert detections == []


def test_postprocess_tflite_detections_respects_num_detections_padding():
    # The TFLite op zero-pads boxes/classes/scores to a fixed size; only the
    # first num_detections entries are real.
    detections = postprocess_tflite_detections(
        boxes=[[0, 0, 1, 1], [0, 0, 0, 0]],
        class_ids=[0, 0],
        scores=[0.9, 0.9],  # second one would also pass threshold if not excluded
        num_detections=1,
        labels=["person"],
        frame_width=10,
        frame_height=10,
        confidence_threshold=0.5,
    )
    assert len(detections) == 1


def test_load_tflite_labels_drops_leading_placeholder(tmp_path):
    labelmap = tmp_path / "labelmap.txt"
    labelmap.write_text("???\nperson\nbicycle\ncar\n")

    labels = load_tflite_labels(labelmap)

    assert labels == ["person", "bicycle", "car"]
    # class index 0 from the model must map to "person", not the placeholder
    assert labels[0] == "person"


def test_load_tflite_labels_keeps_list_when_no_placeholder(tmp_path):
    labelmap = tmp_path / "labelmap.txt"
    labelmap.write_text("person\nbicycle\n")

    labels = load_tflite_labels(labelmap)

    assert labels == ["person", "bicycle"]
