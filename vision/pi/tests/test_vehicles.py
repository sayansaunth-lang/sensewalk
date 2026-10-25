from vision.pi.src.detector import Detection, count_vehicles, nearest_vehicle


def test_nearest_vehicle_picks_the_biggest_nearby_motor_vehicle():
    dets = [
        Detection("person", 0.9, (0, 0, 80, 400)),     # a person, not a vehicle
        Detection("bicycle", 0.9, (0, 0, 80, 400)),    # bicycles are not counted
        Detection("car", 0.8, (0, 0, 100, 250)),       # near (250/480 > 0.45)
        Detection("truck", 0.7, (0, 0, 100, 350)),     # nearer-looking
        Detection("bus", 0.9, (0, 0, 30, 60)),         # far
    ]
    best = nearest_vehicle(dets, frame_height=480)
    assert best is not None and best.label == "truck"


def test_nearest_vehicle_none_when_all_far_or_absent():
    assert nearest_vehicle([Detection("car", 0.9, (0, 0, 30, 60))], 480) is None
    assert nearest_vehicle([], 480) is None


def test_count_vehicles_counts_motor_vehicles_only():
    dets = [
        Detection("car", 0.9, (0, 0, 10, 10)),
        Detection("motorcycle", 0.6, (0, 0, 10, 10)),
        Detection("motorbike", 0.6, (0, 0, 10, 10)),
        Detection("bicycle", 0.9, (0, 0, 10, 10)),
        Detection("person", 0.9, (0, 0, 10, 10)),
    ]
    assert count_vehicles(dets) == 3
