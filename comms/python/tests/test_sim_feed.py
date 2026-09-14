import time

from comms.python.sim_feed import DEFAULT_SCENARIO, SimulatedFeed
from fusion.state_machine import Decision, HazardKind, SensorFusion, State


def test_default_scenario_is_chronologically_ordered():
    times = [e.at_s for e in DEFAULT_SCENARIO]
    assert times == sorted(times)


def test_tick_applies_events_up_to_elapsed_time(monkeypatch):
    feed = SimulatedFeed(loop=False)

    fake_now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])
    feed._start = 1000.0

    fake_now[0] = 1000.0
    snap = feed.tick()
    assert snap.tof_gnd_mm == 300  # nominal walking applied at t=0

    fake_now[0] = 1002.5  # past the t=2.0 ground-dropoff event
    snap = feed.tick()
    assert snap.tof_gnd_mm == 500


def test_full_scenario_drives_fusion_through_multiple_states(monkeypatch):
    feed = SimulatedFeed(loop=False)
    fusion = SensorFusion()

    fake_now = [2000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])
    feed._start = 2000.0

    seen_states: set[State] = set()
    seen_hazards: set[HazardKind] = set()

    for step in range(0, 130):  # 0.1s steps across the ~12s scenario
        fake_now[0] = 2000.0 + step * 0.1
        snap = feed.tick()
        decision: Decision = fusion.update(snap)
        seen_states.add(decision.state)
        seen_hazards.add(decision.hazard)

    assert State.BRAKE_ENGAGED in seen_states
    assert State.FALL_ALERT in seen_states
    assert HazardKind.GROUND_DROPOFF in seen_hazards
    assert HazardKind.OBSTACLE_CLOSE in seen_hazards
    assert len(seen_states) >= 4


def test_loop_restarts_after_duration(monkeypatch):
    feed = SimulatedFeed(loop=True)
    fake_now = [3000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])
    feed._start = 3000.0

    fake_now[0] = 3000.0 + feed._duration + 0.5
    feed.tick()
    # after looping, elapsed resets near 0 -> nominal walking values again
    assert feed.snapshot.tof_gnd_mm == 300
