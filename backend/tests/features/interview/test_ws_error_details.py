from app.features.interview.ws import _error


def test_error_without_details_keeps_the_existing_json_shape():
    event = _error("answer_rejected")

    assert set(event) == {"type", "reason", "recoverable", "code", "step", "occurredAt"}
    assert event["code"] == "ERR_ANSWER_REJECTED"
    assert event["recoverable"] is True
    assert event["step"] is None


def test_error_with_details_adds_only_the_details_key():
    plain = _error("answer_too_long")
    event = _error("answer_too_long", details={"cause": "audio_too_long", "limitSeconds": 180})

    assert set(event) == set(plain) | {"details"}
    assert event["details"] == {"cause": "audio_too_long", "limitSeconds": 180}
    assert event["code"] == "ERR_ANSWER_TOO_LONG"
