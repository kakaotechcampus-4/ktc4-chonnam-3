"""``devon_ai.llm_tasks.report`` 의 BE 연결 경계.

리포트 생성 로직(프롬프트 구성·출력 schema·재요청)은 AI 모듈이 소유한다. 이 모듈은 AI 모듈이
따라야 할 호출 형태(Protocol)와, 모듈 출력을 저장 전에 다시 검증하는 책임만 갖는다.
AI 모듈이 아직 없으면 ``ReportModuleUnavailableError`` 로 실패하며 BE가 대신 생성하지 않는다.
점수 검증 규칙은 spec/backend/features/report.md 의 점수 절을 따른다.
"""

import importlib
import math
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from devon_ai import contracts as c

from app.db.models.interview import PERSONAS
from app.db.models.report import SCORE_KEYS

type ModelCall = Callable[
    [c.ModelRequest, Callable[[object], object]], Awaitable[c.ModelResult[object]]
]


class ReportModuleUnavailableError(RuntimeError):
    """AI의 report 모듈 또는 진입 함수가 없을 때 발생한다."""


class ReportDraftInvalidError(ValueError):
    """AI 모듈 출력이 저장 가능한 모양이 아닐 때 발생한다. 값을 보정해 저장하지 않는다."""


@dataclass(frozen=True)
class ScoreDraft:
    score: float
    reason: str | None
    evidence_turn_nos: tuple[int, ...]


@dataclass(frozen=True)
class FeedbackDraft:
    persona: str
    tags: tuple[str, ...]
    strengths: tuple[str, ...]
    improvements: tuple[str, ...]


@dataclass(frozen=True)
class ReportDraft:
    """검증을 통과한 AI 출력. total_score 는 6개 점수의 단순 평균이다."""

    headline: str
    summary: str
    scores: Mapping[str, ScoreDraft]
    feedbacks: tuple[FeedbackDraft, ...]
    total_score: float


class ReportGenerator(Protocol):
    """AI 모듈 ``generate_report`` 가 따라야 할 호출 형태.

    payload 는 BE가 모은 문답·분석·근거 입력이고, 반환값은 검증 전 원문 객체다.
    공급자 호출은 주입된 model_call(BE gateway) 로만 한다.
    """

    async def __call__(
        self,
        payload: Mapping[str, object],
        *,
        prompt: c.PromptSpec,
        limits: c.CallLimits,
        model_call: ModelCall,
    ) -> Mapping[str, object]: ...


def resolve_generator() -> ReportGenerator:
    """AI report 모듈의 ``generate_report`` 를 찾는다. 없으면 대체 구현 없이 실패한다."""
    try:
        module = importlib.import_module("devon_ai.llm_tasks.report")
    except ImportError as error:
        raise ReportModuleUnavailableError("devon_ai.llm_tasks.report") from error
    generator = getattr(module, "generate_report", None)
    if not callable(generator):
        raise ReportModuleUnavailableError("generate_report")
    return cast(ReportGenerator, generator)


def validate_draft(raw: object) -> ReportDraft:
    """AI 출력을 검증하고 단순 평균 total_score 를 계산한다.

    점수 key 는 SCORE_KEYS 6개와 정확히 같아야 하고 각 값은 0~100 유한 number 다(bool 제외).
    누락·null·범위 밖 값을 0점이나 평균으로 채우지 않는다.
    """
    data = _mapping(raw, "report")
    headline = _text(data.get("headline"), "headline")
    summary = _text(data.get("summary"), "summary")
    raw_scores = _mapping(data.get("scores"), "scores")
    if set(raw_scores) != set(SCORE_KEYS):
        raise ReportDraftInvalidError("scores.keys")
    scores = {key: _score(key, raw_scores[key]) for key in SCORE_KEYS}
    total = round(sum(item.score for item in scores.values()) / len(SCORE_KEYS), 2)
    return ReportDraft(
        headline=headline,
        summary=summary,
        scores=scores,
        feedbacks=_feedbacks(data.get("feedbacks")),
        total_score=total,
    )


def _score(key: str, raw: object) -> ScoreDraft:
    item = _mapping(raw, f"scores.{key}")
    value = item.get("score")
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 100
    ):
        raise ReportDraftInvalidError(f"scores.{key}.score")
    reason = item.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise ReportDraftInvalidError(f"scores.{key}.reason")
    turns = item.get("evidence_turn_nos", [])
    if not isinstance(turns, Sequence) or isinstance(turns, str):
        raise ReportDraftInvalidError(f"scores.{key}.evidence_turn_nos")
    if any(isinstance(n, bool) or not isinstance(n, int) or n < 1 for n in turns):
        raise ReportDraftInvalidError(f"scores.{key}.evidence_turn_nos")
    return ScoreDraft(float(value), reason, tuple(turns))


def _feedbacks(raw: object) -> tuple[FeedbackDraft, ...]:
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        raise ReportDraftInvalidError("feedbacks")
    out: list[FeedbackDraft] = []
    for index, entry in enumerate(raw):
        item = _mapping(entry, f"feedbacks[{index}]")
        persona = item.get("persona")
        if persona not in PERSONAS:
            raise ReportDraftInvalidError(f"feedbacks[{index}].persona")
        out.append(
            FeedbackDraft(
                persona=str(persona),
                tags=_strings(item.get("tags"), f"feedbacks[{index}].tags"),
                strengths=_strings(item.get("strengths"), f"feedbacks[{index}].strengths"),
                improvements=_strings(item.get("improvements"), f"feedbacks[{index}].improvements"),
            )
        )
    if len({f.persona for f in out}) != len(out):
        raise ReportDraftInvalidError("feedbacks.persona_duplicate")
    return tuple(out)


def _strings(raw: object, name: str) -> tuple[str, ...]:
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        raise ReportDraftInvalidError(name)
    if any(not isinstance(v, str) for v in raw):
        raise ReportDraftInvalidError(name)
    return tuple(raw)


def _mapping(raw: object, name: str) -> Mapping[str, object]:
    if not isinstance(raw, Mapping):
        raise ReportDraftInvalidError(name)
    return cast(Mapping[str, object], raw)


def _text(raw: object, name: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ReportDraftInvalidError(name)
    return raw
