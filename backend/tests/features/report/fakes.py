"""report 생성 테스트 공용 대역. 실제 LLM 은 호출하지 않는다. task-16"""

import copy

from app.core.config import LLMSettings
from app.db.models.report import SCORE_KEYS

SCORES = (80, 70, 60, 90, 50, 100)
OUTPUT = {
    "headline": "한 줄 총평",
    "summary": "종합 의견",
    "scores": {
        key: {"score": value, "reason": "근거", "evidence_turn_nos": [1]}
        for key, value in zip(SCORE_KEYS, SCORES, strict=True)
    },
    "feedbacks": [
        {"persona": "tech_lead", "tags": ["t"], "strengths": ["s"], "improvements": ["i"]}
    ],
}
LLM = LLMSettings(
    openai_api_key="k",
    llm_default_model="m",
    llm_timeout_seconds=5,
    llm_max_output_tokens=100,
    llm_max_input_bytes=100000,
    llm_max_response_bytes=100000,
)


class FakeGenerator:
    """generate_report 대역. 호출 횟수와 받은 payload 를 기록한다."""

    def __init__(self, output=None, error=None):
        self.output = copy.deepcopy(OUTPUT) if output is None else output
        self.error = error
        self.calls = []

    async def __call__(self, payload, *, prompt, limits, model_call):
        self.calls.append(payload)
        if self.error:
            raise self.error
        return self.output
