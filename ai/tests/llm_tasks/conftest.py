import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from devon_ai import contracts as c
from devon_ai.llm_tasks import answer_analysis

REF = "a" * 40
OTHER_REF = "b" * 40
PROMPT = c.PromptSpec("answer_analysis", "answer_analysis_v1", "fixture-model", "template")
LIMITS = c.CallLimits(1, 512, 65536, 65536)
ANSWER = "조회가 많아서 DB 부하를 줄이려고 캐시했습니다."


def metadata() -> c.AttemptMetadata:
    return c.AttemptMetadata(1, "fixture", "fixture-model", "answer_analysis_v1", "1", 2, None, 12)


class Provider:
    """외부 모델 대역. 파싱·의미 검증은 실제 검증기를 그대로 쓴다."""

    def __init__(self, output: object) -> None:
        self.output = json.loads(json.dumps(output))
        self.requests: list[c.ModelRequest] = []

    async def __call__(self, request, validator):
        self.requests.append(request)
        try:
            data = validator(self.output)
        except c.ContractError as exc:
            return c.ModelResult(
                None, c.CallFailure(exc.stage, "llm_failed", "invalid"), (metadata(),)
            )
        return c.ModelResult(data, None, (metadata(),))


def make_contract() -> c.QuestionContract:
    return c.QuestionContract(
        "조회·수정 특성과 캐시 선정 이유",
        (
            c.RequiredPoint("read_pattern", "조회 특성"),
            c.RequiredPoint("write_pattern", "수정 특성"),
            c.RequiredPoint("cache_purpose", "캐시 선정 목적"),
        ),
        (),
        (),
        "캐시 선정 판단",
    )


def make_context(**changes) -> c.Context:
    history = (
        c.HistoryTurn(
            "turn-1", "hr_manager", "역할을 소개해 주세요.", "백엔드를 맡았습니다.", None
        ),
        c.HistoryTurn("turn-2", "tech_lead", "DB는 무엇을 썼나요?", "PostgreSQL입니다.", None),
    )
    base = c.Context(
        "interview-1",
        "turn-3",
        3,
        9,
        (),
        ("tech_lead",),
        (),
        (c.ContextRepository("repo-1", REF, True, (), ()),),
        history,
        make_contract(),
        (),
        (),
        c.ContextLimits(2, 0, "fixture"),
    )
    return replace(base, **changes)


def checked_question(contract: c.QuestionContract | None = None) -> c.ContractChecked[c.Question]:
    contract = contract or make_contract()
    candidate = c.Question(
        "tech_lead", "이 서비스에서 캐시를 선택한 이유를 설명해 주세요.", "cache", contract, (), ()
    )
    return c.validate_question(
        candidate,
        review=c.QuestionReview(candidate.text, contract),
        allowed_personas=("tech_lead",),
        evidence_refs=frozenset(),
        basis_refs=frozenset(),
        jd_requirement_ids=frozenset(),
    )


def analysis_output(**changes) -> dict[str, object]:
    """질문 필수 항목 중 조회 특성·선정 목적만 확인한 부분 충족 분석."""
    output: dict[str, object] = {
        "evaluation_status": "evaluated",
        "sufficiency": "partial",
        "covered_points": [
            {"key": "read_pattern", "answer_quotes": ["조회가 많아서"]},
            {"key": "cache_purpose", "answer_quotes": ["DB 부하를 줄이려고 캐시했습니다"]},
        ],
        "missing_points": ["write_pattern"],
        "technical_assessment": {
            "explanation": "읽기 비중이 높은 데이터에 캐시를 적용한 설명은 타당하다.",
            "answer_quotes": ["DB 부하를 줄이려고"],
            "evidence_refs": [],
            "limitations": [],
        },
        "contribution_scope": {"scope": "unknown", "answer_quotes": []},
        "claim_checks": [],
        "needs_verification": False,
        "verification_requests": [],
        "limitations": ["답변에 기여 범위 언급이 없다."],
    }
    output.update(changes)
    return output


@pytest.fixture
def run():
    def _run(provider, *, context=None, question=None, answer=ANSWER, **options):
        return asyncio.run(
            answer_analysis.analyze_answer(
                context or make_context(),
                question or checked_question(),
                turn_id=options.pop("turn_id", "turn-3"),
                answer_text=answer,
                prompt=options.pop("prompt", PROMPT),
                limits=LIMITS,
                model_call=provider,
                **options,
            )
        )

    return _run


@pytest.fixture
def kit():
    # importlib 모드에서는 conftest를 import할 수 없어 필요한 도우미를 fixture로 노출한다.
    return SimpleNamespace(
        Provider=Provider,
        analysis_output=analysis_output,
        make_context=make_context,
        make_contract=make_contract,
        checked_question=checked_question,
        metadata=metadata,
        REF=REF,
        OTHER_REF=OTHER_REF,
        ANSWER=ANSWER,
        PROMPT=PROMPT,
    )
