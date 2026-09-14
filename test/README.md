# Test Data & Field Trial Records

Owned by C4 (E2 in the learning roadmap). This directory holds the actual measured numbers the final report quotes — not estimates, not one lucky run. See [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) and [`FIELD_TEST_PLAN.md`](FIELD_TEST_PLAN.md) for what's being measured and why.

## Layout

```
test/
  data/        Recorded test clips, raw sensor logs (gitignored: *.mp4/*.avi)
  logs/        CSV output from bench/field test runs (heartbeat test, detection logs, latency tables)
  FIELD_TEST_PLAN.md          Written test plan (braking distance, false-positive rate, battery life) — Phase 5, but write it now
  analyze_detection_log.py    Computes false-positive/false-negative rate from a logged detection CSV (B2 deliverable)
```

## CSV schemas

**Ground/obstacle detection log** (B2 deliverable — 50+ walks over a known pothole/curb, 50+ over flat ground):

```
timestamp,scenario,tof_gnd_mm,tof_gnd_baseline_mm,detected_hazard,ground_truth_hazard
```

- `scenario`: free-text label for the test run (e.g. `pothole_15cm`, `flat_ground`)
- `detected_hazard` / `ground_truth_hazard`: `0` or `1`

Analyze with:

```bash
python3 test/analyze_detection_log.py test/logs/your_detection_log.csv
```

which prints true/false positive/negative counts and rates.

**Heartbeat / UART link validation** (D1 deliverable): produced by `comms/python/heartbeat_test.py`, schema `seq,value_ms,t_wall`.

**TTS latency table** (E1 deliverable): produced by `speech.tts.AlertSpeaker.write_latency_log()`, schema `phrase_key,trigger_to_sound_ms`.

**Fall detection log** (D2 deliverable — 15+ controlled, padded, safe test drops): schema `timestamp,trial_id,min_accel_millig,max_accel_millig,orientation_delta_centideg,detected_fall,ground_truth_fall`.

## Honesty rule

Every table above exists to be quoted with real numbers in the final report, including when those numbers are worse than a tutorial's cherry-picked demo. An honest "detects potholes 80% of the time under these lighting/speed conditions" is a stronger engineering result than an unverified claim of perfection — this is stated explicitly in the learning roadmap's closing notes, and it's the whole reason this directory exists instead of just a demo video.
