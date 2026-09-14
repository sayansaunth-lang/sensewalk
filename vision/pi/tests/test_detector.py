from vision.pi.src.detector import Detection, any_hazard_relevant


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
