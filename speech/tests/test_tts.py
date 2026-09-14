from speech.tts import AlertSpeaker


class FakeEngine:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)

    def runAndWait(self):
        pass

    def setProperty(self, *_args, **_kwargs):
        pass


def test_speak_uses_engine_when_available():
    speaker = AlertSpeaker.__new__(AlertSpeaker)  # bypass pyttsx3.init()
    speaker._engine = FakeEngine()
    speaker._last_spoken_at = {}
    speaker.latency_log = []

    record = speaker.speak("pothole_ahead")

    assert speaker._engine.said == ["Pothole ahead, stopping"]
    assert record is not None
    assert record.phrase_key == "pothole_ahead"
    assert record.trigger_to_sound_ms >= 0
    assert len(speaker.latency_log) == 1


def test_speak_suppresses_rapid_repeats():
    speaker = AlertSpeaker.__new__(AlertSpeaker)
    speaker._engine = FakeEngine()
    speaker._last_spoken_at = {}
    speaker.latency_log = []

    speaker.speak("obstacle_close", min_repeat_interval_s=10)
    second = speaker.speak("obstacle_close", min_repeat_interval_s=10)

    assert second is None
    assert speaker._engine.said == ["Obstacle close, stopping"]


def test_speak_disabled_when_no_engine(capsys):
    speaker = AlertSpeaker.__new__(AlertSpeaker)
    speaker._engine = None
    speaker._last_spoken_at = {}
    speaker.latency_log = []

    result = speaker.speak("fall_alert")

    assert result is None
    assert speaker.available is False
    captured = capsys.readouterr()
    assert "Fall detected" in captured.out


def test_write_latency_log(tmp_path):
    speaker = AlertSpeaker.__new__(AlertSpeaker)
    speaker._engine = FakeEngine()
    speaker._last_spoken_at = {}
    speaker.latency_log = []

    speaker.speak("person_close")
    out_file = tmp_path / "latency.csv"
    speaker.write_latency_log(out_file)

    content = out_file.read_text()
    assert "phrase_key" in content
    assert "person_close" in content
