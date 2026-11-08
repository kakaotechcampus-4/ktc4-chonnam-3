"""명시적인 질문 재생 요청만 답변과 분리한다.

지원 문법 밖의 자유 발화 전체를 이해한다고 가정하지 않는다. 전체 발화 일치만
사용하고, 기술 설명·인용 속의 '다시'를 명령으로 해석하지 않는다.
"""

from __future__ import annotations

from typing import Literal, Protocol

ReplayKind = Literal["repeat_question", "answer", "uncertain"]


class ReplayIntentClassifier(Protocol):
    async def classify(self, text: str, question: str) -> ReplayKind: ...


class ExplicitReplayCommands:
    _COMMANDS = frozenset(
        {
            "다시말씀해주세요",
            "다시말씀해주실수있나요",
            "다시말씀해주시겠어요",
            "한번더말씀해주세요",
            "한번더말씀해주실수있나요",
            "다시들려주세요",
            "한번더들려주세요",
            "다시읽어주세요",
            "한번더읽어주세요",
        }
    )

    def is_explicit(self, text: str) -> bool:
        if len(text) > 100:
            return False
        compact = "".join(text.split()).rstrip(".!?。！？")
        for prefix in ("죄송하지만", "죄송한데"):
            if compact.startswith(prefix):
                compact = compact[len(prefix) :]
                break
        if compact.startswith("방금"):
            compact = compact[2:]
        for prefix in ("질문을", "질문"):
            if compact.startswith(prefix):
                compact = compact[len(prefix) :]
                break
        return compact in self._COMMANDS


async def should_replay(
    text: str, question: str, classifier: ReplayIntentClassifier | None = None
) -> bool:
    if ExplicitReplayCommands().is_explicit(text):
        return True
    # 정상 모름 응답은 재생으로 돌려 평가·답변 기록에서 사라지게 하지 않는다.
    if "".join(text.split()).rstrip(".!?。！？") in {
        "모르겠습니다",
        "잘모르겠습니다",
        "모르겠어요",
        "잘모르겠어요",
    }:
        return False
    if classifier is None:
        return False
    try:
        return await classifier.classify(text, question) == "repeat_question"
    except Exception:
        # 분류 오류로 사용자의 실제 답변을 버리지 않는다. 공급자 원문은 기록하지 않는다.
        return False
