"""턴별 답변 오디오 임시 버퍼와 답변 메시지 판정. 메모리에만 두며 원본을 저장하지 않는다(0007).

WS·STT·DB를 모르는 순수 로직이라 시계를 주입해 단위 테스트한다. 연결마다 하나를 만들고
연결이 끝나면 버려 미완료 오디오가 남지 않게 한다.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import INTERVIEW_MAX_TURNS

MAX_MIME_LENGTH = 100
AUDIO_TOO_LONG_CAUSE = "audio_too_long"


@dataclass(frozen=True)
class AnswerAudioLimits:
    max_bytes: int
    max_seconds: float
    grace_seconds: float
    idle_timeout_seconds: float

    @property
    def deadline_seconds(self) -> float:
        """answerStart 이후 서버가 기다리는 최대 수신 시간(상한 + 여유)."""
        return self.max_seconds + self.grace_seconds


@dataclass(frozen=True)
class AnswerAudio:
    turn: int
    mime_type: str
    data: bytes


class AnswerAudioTooLong(Exception):
    """시간 또는 누적 바이트 상한 초과. 미완료 버퍼는 이미 버려진 상태다."""


class NoActiveAnswer(Exception):
    """answerStart 없이 answerEnd가 왔거나 다른 턴의 answerEnd가 왔다."""


class AnswerAudioBuffer:
    def __init__(
        self, limits: AnswerAudioLimits, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._limits = limits
        self._clock = clock
        self._turn: int | None = None
        self._mime = ""
        self._chunks: list[bytes] = []
        self._size = 0
        self._started_at = 0.0
        self._last_activity = 0.0

    @property
    def active_turn(self) -> int | None:
        return self._turn

    def start(self, turn: int, mime_type: str) -> None:
        """같은 턴이든 아니든 받던 오디오는 버리고 새로 받는다."""
        self.discard()
        now = self._clock()
        self._turn, self._mime = turn, mime_type
        self._started_at = self._last_activity = now

    def append(self, chunk: bytes) -> None:
        """진행 중이 아니면 무시한다. 상한을 넘으면 버퍼를 버리고 예외를 낸다."""
        if self._turn is None:
            return
        self._check_limits(extra=len(chunk))
        self._chunks.append(chunk)
        self._size += len(chunk)
        self._last_activity = self._clock()

    def end(self, turn: int) -> AnswerAudio:
        """받은 오디오를 돌려주며 버퍼를 비운다. 시간이 이미 상한을 넘었으면 초과다."""
        if self._turn is None or self._turn != turn:
            raise NoActiveAnswer
        self._check_limits(extra=0)
        audio = AnswerAudio(turn, self._mime, b"".join(self._chunks))
        self.discard()
        return audio

    def discard(self) -> None:
        self._turn = None
        self._chunks = []
        self._size = 0

    def idle_remaining(self) -> float | None:
        """다음 오디오 프레임을 기다릴 수 있는 남은 시간. 진행 중이 아니면 None."""
        if self._turn is None:
            return None
        return max(0.0, self._last_activity + self._limits.idle_timeout_seconds - self._clock())

    def discard_if_idle(self) -> bool:
        remaining = self.idle_remaining()
        if remaining is None or remaining > 0:
            return False
        self.discard()
        return True

    def _check_limits(self, *, extra: int) -> None:
        if (
            self._size + extra > self._limits.max_bytes
            or self._clock() - self._started_at > self._limits.deadline_seconds
        ):
            self.discard()
            raise AnswerAudioTooLong


@dataclass(frozen=True)
class AnswerStart:
    turn: int
    mime_type: str


@dataclass(frozen=True)
class AnswerEnd:
    turn: int


def _turn(raw: dict[str, object]) -> int | None:
    value = raw.get("turn")
    if type(value) is not int or not 1 <= value <= INTERVIEW_MAX_TURNS:
        return None
    return value


def parse_voice_message(raw: object) -> AnswerStart | AnswerEnd | None:
    """`answerStart`·`answerEnd`만 해석한다. 다른 메시지나 형식 위반은 None이다."""
    if type(raw) is not dict:
        return None
    turn = _turn(raw)
    if turn is None:
        return None
    if raw.get("type") == "answerEnd" and set(raw) == {"type", "turn"}:
        return AnswerEnd(turn)
    mime = raw.get("mimeType")
    if (
        raw.get("type") == "answerStart"
        and set(raw) == {"type", "turn", "mimeType"}
        and type(mime) is str
        and 0 < len(mime) <= MAX_MIME_LENGTH
        and mime.lower().startswith("audio/")
        and mime.isprintable()
    ):
        return AnswerStart(turn, mime)
    return None


def turn_rejection(turn: int, current_turn: int, answerable_turn: int | None) -> str | None:
    """`answerStart`를 받아도 되는지 판정한다. 허용이면 None, 아니면 error reason을 돌려준다.

    - 지나간 턴(`turn < current_turn`): `answer_stale_turn`. 다음 질문으로 넘어간 뒤의 늦은 메시지.
    - 그 밖에 답변할 수 없는 턴: `answer_rejected`. 아직 오지 않은 턴, 현재 턴이지만 이미 답변이
      저장됐거나 다음 질문을 만드는 중인 경우다.
    """
    if turn < current_turn:
        return "answer_stale_turn"
    if answerable_turn is None or turn != answerable_turn:
        return "answer_rejected"
    return None
