import time

from fusion.state_machine import (
    Decision,
    HazardKind,
    SensorFusion,
    SensorSnapshot,
    State,
)


def make_snapshot(**overrides) -> SensorSnapshot:
    base = SensorSnapshot(grip_left=True, grip_right=True, last_grip_at=time.monotonic())
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def test_starts_idle():
    fusion = SensorFusion()
    assert fusion.state is State.IDLE


def test_nominal_walking_with_grip():
    fusion = SensorFusion()
    decision = fusion.update(make_snapshot())
    assert decision.state is State.WALKING
    assert decision.hazard is HazardKind.NONE


def test_ground_dropoff_triggers_brake():
    fusion = SensorFusion()
    snap = make_snapshot(tof_gnd_mm=500, tof_gnd_baseline_mm=300)  # +200mm > 150mm threshold
    decision = fusion.update(snap)
    assert decision.state is State.BRAKE_ENGAGED
    assert decision.hazard is HazardKind.GROUND_DROPOFF
    assert decision.alert_phrase_key == "pothole_ahead"


def test_obstacle_close_triggers_brake():
    fusion = SensorFusion()
    snap = make_snapshot(us_c_cm=25)
    decision = fusion.update(snap)
    assert decision.state is State.BRAKE_ENGAGED
    assert decision.hazard is HazardKind.OBSTACLE_CLOSE


def test_ground_dropoff_outranks_person_nearby_when_both_present():
    # D4 requirement: test the fused system against combined scenarios.
    fusion = SensorFusion()
    snap = make_snapshot(
        tof_gnd_mm=600,
        tof_gnd_baseline_mm=300,
        vision_person_nearby=True,
    )
    decision = fusion.update(snap)
    assert decision.hazard is HazardKind.GROUND_DROPOFF
    assert decision.state is State.BRAKE_ENGAGED


def test_obstacle_outranks_person_nearby():
    fusion = SensorFusion()
    snap = make_snapshot(us_l_cm=20, vision_person_nearby=True)
    decision = fusion.update(snap)
    assert decision.hazard is HazardKind.OBSTACLE_CLOSE


def test_person_nearby_alone_is_warning_not_brake():
    fusion = SensorFusion()
    decision = fusion.update(make_snapshot(vision_person_nearby=True))
    assert decision.state is State.HAZARD_WARNING
    assert decision.alert_phrase_key == "person_close"


def test_sign_read_never_escalates_past_walking():
    fusion = SensorFusion()
    decision = fusion.update(make_snapshot(ocr_text="ROOM 204"))
    assert decision.state is State.WALKING
    assert decision.hazard is HazardKind.SIGN_READ
    assert decision.alert_phrase_key == "sign_read"


def test_fall_flag_always_wins():
    fusion = SensorFusion()
    snap = make_snapshot(
        tof_gnd_mm=600,
        tof_gnd_baseline_mm=300,
        vision_person_nearby=True,
        fall_flag=True,
    )
    decision = fusion.update(snap)
    assert decision.state is State.FALL_ALERT
    assert decision.alert_phrase_key == "fall_alert"


def test_brake_holds_until_hazard_clears_and_grip_reengaged():
    fusion = SensorFusion()
    fusion.update(make_snapshot(us_c_cm=10))
    assert fusion.state is State.BRAKE_ENGAGED

    # hazard clears but grip is off -> stay engaged
    decision = fusion.update(make_snapshot(grip_left=False, grip_right=False))
    assert decision.state is State.BRAKE_ENGAGED

    # hazard clear + grip back on -> release
    decision = fusion.update(make_snapshot(grip_left=True, grip_right=True))
    assert decision.state is State.WALKING


def test_idle_after_grip_release_timeout():
    fusion = SensorFusion()
    fusion.update(make_snapshot())
    stale_snap = make_snapshot(
        grip_left=False,
        grip_right=False,
        last_grip_at=time.monotonic() - 10,
    )
    decision = fusion.update(stale_snap)
    assert decision.state is State.IDLE


def test_history_records_transitions():
    fusion = SensorFusion()
    fusion.update(make_snapshot())
    fusion.update(make_snapshot(us_c_cm=10))
    history = fusion.history()
    assert (State.IDLE, State.WALKING, "nominal") in history
    assert any(t[1] is State.BRAKE_ENGAGED for t in history)


def test_four_state_cycle_matches_roadmap_deliverable():
    """D4 deliverable: 'a working demo cycling correctly through at least 4
    states during a single test walk.'"""
    fusion = SensorFusion()
    seen: set[State] = set()

    seen.add(fusion.update(make_snapshot()).state)  # WALKING
    seen.add(fusion.update(make_snapshot(us_c_cm=15)).state)  # BRAKE_ENGAGED
    seen.add(fusion.update(make_snapshot()).state)  # WALKING again (hazard clear + grip)
    seen.add(
        fusion.update(
            make_snapshot(grip_left=False, grip_right=False, last_grip_at=time.monotonic() - 10)
        ).state
    )  # IDLE
    seen.add(fusion.update(make_snapshot(fall_flag=True)).state)  # FALL_ALERT

    assert len(seen) >= 4
