import wave
from pathlib import Path

from speech import clips, phrases
from speech.tts import AlertSpeaker


class FakeEngine:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)

    def runAndWait(self):
        pass


def make_speaker(clip_map, engine=None):
    speaker = AlertSpeaker.__new__(AlertSpeaker)  # bypass pyttsx3.init()
    speaker._engine = engine
    speaker._clips = clip_map
    speaker._last_spoken_at = {}
    speaker.latency_log = []
    return speaker


def test_every_mapped_clip_exists_and_is_a_valid_wav():
    loaded = clips.load_clips()
    assert set(loaded) == set(clips.CLIP_FOR_PHRASE)
    for key, path in loaded.items():
        with wave.open(str(path), "rb") as w:
            assert w.getnchannels() == 1 and w.getsampwidth() == 2
            assert 1.0 < w.getnframes() / w.getframerate() < 8.0, key


def test_every_clip_key_is_a_real_phrase():
    for key in clips.CLIP_FOR_PHRASE:
        assert key in phrases.VOCABULARY


def test_clip_is_played_instead_of_tts(monkeypatch):
    played = []
    monkeypatch.setattr(clips, "play_clip", lambda p, sev=0: played.append(p) or True)
    engine = FakeEngine()
    speaker = make_speaker(clips.load_clips(), engine)

    record = speaker.speak("obstacle_close")

    assert record is not None
    assert [p.name for p in played] == ["obstacle_warning.wav"]
    assert engine.said == []  # the synthesised voice stayed silent


def test_falls_back_to_tts_when_the_clip_cannot_play(monkeypatch):
    monkeypatch.setattr(clips, "play_clip", lambda p, sev=0: False)
    engine = FakeEngine()
    speaker = make_speaker(clips.load_clips(), engine)

    speaker.speak("obstacle_close")

    assert engine.said == ["Obstacle close, stopping"]


def test_phrase_without_a_clip_still_uses_tts(monkeypatch):
    monkeypatch.setattr(clips, "play_clip", lambda p, sev=0: True)
    engine = FakeEngine()
    speaker = make_speaker(clips.load_clips(), engine)

    speaker.speak("alert_sent")

    assert engine.said == ["Emergency message sent"]


def test_clip_repeat_is_suppressed(monkeypatch):
    played = []
    monkeypatch.setattr(clips, "play_clip", lambda p, sev=0: played.append(p) or True)
    speaker = make_speaker(clips.load_clips(), FakeEngine())

    speaker.speak("pothole_ahead", min_repeat_interval_s=10)
    assert speaker.speak("pothole_ahead", min_repeat_interval_s=10) is None
    assert len(played) == 1


def test_missing_clip_file_is_left_out(tmp_path: Path):
    assert clips.load_clips(tmp_path) == {}


def test_available_when_only_clips_exist():
    assert make_speaker(clips.load_clips(), None).available is True
    assert make_speaker({}, None).available is False


class RecordingPlayer(clips.ClipPlayer):
    """ClipPlayer with the OS audio calls replaced, so priority logic can be tested silently."""

    def __init__(self):
        super().__init__()
        self.started, self.stopped = [], []

    def _start(self, path):
        self.started.append(path.name)
        return path.name

    def _stop(self, handle):
        self.stopped.append(handle)


def test_player_drops_a_clip_while_something_as_urgent_is_playing():
    player = RecordingPlayer()
    path = clips.AUDIO_DIR / "vehicle_ahead.wav"
    assert player.play(path, severity=2, now=100.0)
    assert player.play(clips.AUDIO_DIR / "traffic_ahead.wav", severity=2, now=101.0)  # skipped, still True
    assert player.started == ["vehicle_ahead.wav"]


def test_player_lets_a_more_urgent_clip_interrupt():
    player = RecordingPlayer()
    player.play(clips.AUDIO_DIR / "road_clear.wav", severity=1, now=100.0)
    assert player.play(clips.AUDIO_DIR / "obstacle_warning.wav", severity=3, now=100.5)
    assert player.started == ["road_clear.wav", "obstacle_warning.wav"]
    assert player.stopped == ["road_clear.wav"]


def test_player_plays_the_next_clip_after_the_first_finishes():
    player = RecordingPlayer()
    player.play(clips.AUDIO_DIR / "road_clear.wav", severity=1, now=100.0)  # ~2 s long
    assert player.play(clips.AUDIO_DIR / "road_clear.wav", severity=1, now=110.0)
    assert len(player.started) == 2


def test_player_reports_failure_when_no_backend(monkeypatch):
    player = RecordingPlayer()
    monkeypatch.setattr(player, "_start", lambda path: None)
    assert player.play(clips.AUDIO_DIR / "road_clear.wav", severity=1, now=1.0) is False
