import pytest

from speech import phrases


def test_render_static_phrase():
    assert phrases.render("pothole_ahead") == "Pothole ahead, stopping"


def test_render_templated_phrase_with_kwargs():
    text = phrases.render("sign_read", text="ROOM 204")
    assert text == "ROOM 204"


def test_render_unknown_key_raises():
    with pytest.raises(KeyError):
        phrases.render("not_a_real_phrase")


def test_severity_of_matches_expected_ranking():
    assert phrases.severity_of("sign_read") < phrases.severity_of("person_close")
    assert phrases.severity_of("person_close") < phrases.severity_of("pothole_ahead")


def test_fusion_alert_keys_all_exist_in_vocabulary():
    # fusion/state_machine.py hands out these exact keys — keep them in sync.
    from fusion.state_machine import HazardKind  # noqa: F401  (documents the coupling)

    for key in ["pothole_ahead", "obstacle_close", "person_close", "sign_read", "fall_alert"]:
        assert key in phrases.VOCABULARY
