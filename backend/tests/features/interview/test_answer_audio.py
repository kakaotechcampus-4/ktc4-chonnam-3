import pytest

from app.features.interview.answer_audio import (
    AnswerAudio,
    AnswerAudioBuffer,
    AnswerAudioLimits,
    AnswerAudioTooLong,
    AnswerEnd,
    AnswerStart,
    NoActiveAnswer,
    parse_voice_message,
    turn_rejection,
)

LIMITS = AnswerAudioLimits(
    max_bytes=100, max_seconds=180.0, grace_seconds=5.0, idle_timeout_seconds=10.0
)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def buffer(clock) -> AnswerAudioBuffer:
    return AnswerAudioBuffer(LIMITS, clock)


def test_collects_chunks_in_order_and_empties_after_end(buffer):
    buffer.start(3, "audio/webm;codecs=opus")
    buffer.append(b"ab")
    buffer.append(b"cd")

    assert buffer.end(3) == AnswerAudio(3, "audio/webm;codecs=opus", b"abcd")
    assert buffer.active_turn is None
    with pytest.raises(NoActiveAnswer):
        buffer.end(3)


def test_chunk_without_answer_start_is_ignored(buffer):
    buffer.append(b"stray")
    assert buffer.active_turn is None


def test_restart_on_same_or_other_turn_discards_unfinished_audio(buffer):
    buffer.start(3, "audio/webm")
    buffer.append(b"old")
    buffer.start(3, "audio/webm")
    buffer.append(b"new")
    assert buffer.end(3).data == b"new"

    buffer.start(3, "audio/webm")
    buffer.append(b"x")
    buffer.start(4, "audio/webm")
    assert buffer.end(4).data == b""


def test_end_without_start_or_for_another_turn_is_not_an_active_answer(buffer):
    with pytest.raises(NoActiveAnswer):
        buffer.end(1)
    buffer.start(2, "audio/webm")
    with pytest.raises(NoActiveAnswer):
        buffer.end(3)
    assert buffer.active_turn == 2  # 다른 턴의 answerEnd가 진행 중인 답변을 지우지 않는다.


def test_byte_limit_discards_and_allows_restart_on_same_turn(buffer):
    buffer.start(3, "audio/webm")
    buffer.append(b"x" * 100)
    with pytest.raises(AnswerAudioTooLong):
        buffer.append(b"y")
    assert buffer.active_turn is None

    buffer.start(3, "audio/webm")
    buffer.append(b"ok")
    assert buffer.end(3).data == b"ok"


def test_time_limit_uses_server_receive_time_with_grace(buffer, clock):
    buffer.start(3, "audio/webm")
    clock.now += 185.0  # 180초 + 여유 5초는 아직 허용
    buffer.append(b"a")
    clock.now += 0.1
    with pytest.raises(AnswerAudioTooLong):
        buffer.append(b"b")
    assert buffer.active_turn is None


def test_answer_end_after_deadline_is_too_long(buffer, clock):
    buffer.start(3, "audio/webm")
    buffer.append(b"a")
    clock.now += 186.0
    with pytest.raises(AnswerAudioTooLong):
        buffer.end(3)
    assert buffer.active_turn is None


def test_idle_timeout_discards_when_no_audio_arrives(buffer, clock):
    assert buffer.idle_remaining() is None
    buffer.start(3, "audio/webm")
    clock.now += 9.0
    assert buffer.idle_remaining() == pytest.approx(1.0)
    assert buffer.discard_if_idle() is False

    buffer.append(b"a")  # 오디오가 오면 다시 10초를 기다린다.
    clock.now += 9.0
    assert buffer.discard_if_idle() is False
    clock.now += 1.0
    assert buffer.discard_if_idle() is True
    assert buffer.active_turn is None
    assert buffer.idle_remaining() is None


def test_discard_drops_unfinished_audio_like_a_closed_connection(buffer):
    buffer.start(3, "audio/webm")
    buffer.append(b"abc")
    buffer.discard()
    with pytest.raises(NoActiveAnswer):
        buffer.end(3)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            {"type": "answerStart", "turn": 3, "mimeType": "audio/webm;codecs=opus"},
            AnswerStart(3, "audio/webm;codecs=opus"),
        ),
        ({"type": "answerEnd", "turn": 9}, AnswerEnd(9)),
        ({"type": "answerStart", "turn": 3}, None),
        ({"type": "answerStart", "turn": 3, "mimeType": "text/plain"}, None),
        ({"type": "answerStart", "turn": 3, "mimeType": ""}, None),
        ({"type": "answerStart", "turn": 3, "mimeType": "audio/" + "x" * 100}, None),
        ({"type": "answerStart", "turn": 3, "mimeType": "audio/webm", "extra": 1}, None),
        ({"type": "answerStart", "turn": 0, "mimeType": "audio/webm"}, None),
        ({"type": "answerStart", "turn": 10, "mimeType": "audio/webm"}, None),
        ({"type": "answerStart", "turn": True, "mimeType": "audio/webm"}, None),
        ({"type": "answerEnd", "turn": "3"}, None),
        ({"type": "answerEnd", "turn": 3, "mimeType": "audio/webm"}, None),
        ({"type": "answer", "turn": 3, "text": "x"}, None),
        (b"binary", None),
        ([], None),
    ],
)
def test_parse_voice_message(raw, expected):
    assert parse_voice_message(raw) == expected


@pytest.mark.parametrize(
    ("turn", "current_turn", "answerable_turn", "expected"),
    [
        (3, 3, 3, None),  # 지금 답변할 수 있는 턴
        (2, 3, 3, "answer_stale_turn"),  # 지나간 턴
        (1, 5, None, "answer_stale_turn"),  # 지나간 턴은 현재 질문 유무와 무관하다
        (4, 3, 3, "answer_rejected"),  # 아직 오지 않은 턴
        (3, 3, None, "answer_rejected"),  # 현재 턴이지만 이미 답변됨/다음 질문 생성 중
    ],
)
def test_turn_rejection_separates_stale_from_rejected(
    turn, current_turn, answerable_turn, expected
):
    assert turn_rejection(turn, current_turn, answerable_turn) == expected
