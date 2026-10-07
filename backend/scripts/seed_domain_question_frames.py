"""domain_question_frames 시드. domain_category × axis 조합마다 질문 뼈대 1개(총 21개).

docs/db-schema.md · task-03 근거: spec/backend/features/interview.md

domain_lead 페르소나가 이 frame_text 를 참고해 도메인 관점 질문을 구성한다.
문구는 사용자가 해당 도메인 경험이 있다고 전제하지 않는 가정형("~라면 어떻게 하시겠어요?")이다.
JD 요구사항 추궁이 아니라 "이 도메인이면 흔히 부딪히는 지점"을 짚는 용도라 사용자
답변의 사실 여부를 판정하지 않는다 — director/LLM 이 실제 발화로 바꾼다.

축(app.db.models.knowledge.QUESTION_FRAME_AXES) 3개:
  privacy_sensitive_data   — 개인정보/민감정보
  reliability_operations   — 장애/신뢰성/운영
  user_experience_context  — 사용자 경험/서비스 사용 맥락
"""

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.posting import DOMAIN_CATEGORIES


@dataclass(frozen=True, slots=True)
class DomainQuestionFrameSpec:
    domain_category: str
    axis: str
    frame_text: str


_AXIS_PRIVACY = "privacy_sensitive_data"
_AXIS_RELIABILITY = "reliability_operations"
_AXIS_UX = "user_experience_context"

_FRAME_TEXT_BY_DOMAIN: dict[str, dict[str, str]] = {
    "finance": {
        _AXIS_PRIVACY: (
            "계좌·거래 내역 같은 민감한 금융 정보를 다루는 서비스라면, 접근 권한이나 "
            "로그 노출을 어떻게 제한하시겠어요?"
        ),
        _AXIS_RELIABILITY: (
            "결제·정산처럼 실패가 금전적 손실로 이어지는 흐름에서 장애가 발생한다면, "
            "어떻게 감지하고 복구하시겠어요?"
        ),
        _AXIS_UX: (
            "잔액·거래 결과처럼 숫자 하나의 오차도 신뢰를 깨는 화면이라면, 사용자에게 "
            "상태를 어떻게 명확히 전달하시겠어요?"
        ),
    },
    "game": {
        _AXIS_PRIVACY: (
            "유저 계정·결제 정보와 플레이 로그를 함께 다루는 서비스라면, 개인 식별 정보를 "
            "어떻게 분리해서 취급하시겠어요?"
        ),
        _AXIS_RELIABILITY: (
            "이벤트·업데이트 직후처럼 동시 접속이 몰리는 상황이라면, 서버가 버티도록 "
            "무엇을 고려하시겠어요?"
        ),
        _AXIS_UX: (
            "입력 지연이나 프레임 저하가 체감에 바로 드러나는 상황이라면, 사용자 경험을 "
            "어떻게 확인하고 개선하시겠어요?"
        ),
    },
    "travel": {
        _AXIS_PRIVACY: (
            "예약자 개인정보와 결제·여권 정보를 외부 API 로 넘겨야 한다면, 어떤 기준으로 "
            "최소한만 전달하시겠어요?"
        ),
        _AXIS_RELIABILITY: (
            "외부 항공/숙박 API 가 지연되거나 실패한다면, 예약 흐름을 어떻게 "
            "안전하게 처리하시겠어요?"
        ),
        _AXIS_UX: (
            "여러 단계를 거치는 예약 과정이라면, 사용자가 진행 상태를 어떻게 파악할 수 "
            "있게 하시겠어요?"
        ),
    },
    "shopping": {
        _AXIS_PRIVACY: (
            "주문·배송 정보 같은 개인정보가 여러 서비스(결제·물류)로 흘러가야 한다면, "
            "어떻게 보호하시겠어요?"
        ),
        _AXIS_RELIABILITY: (
            "특가·할인 이벤트로 트래픽이 급증한다면, 재고·주문 정합성을 어떻게 지키시겠어요?"
        ),
        _AXIS_UX: "장바구니·결제처럼 이탈이 잦은 구간이라면, 사용자 편의를 어떻게 개선하시겠어요?",
    },
    "medical": {
        _AXIS_PRIVACY: (
            "진료·건강 정보 같은 민감정보를 다루는 서비스라면, 접근 통제나 익명화를 어떻게 "
            "적용하시겠어요?"
        ),
        _AXIS_RELIABILITY: (
            "예약·처방처럼 실수가 안전 문제로 이어질 수 있는 기능이라면, 검증을 "
            "어떻게 강화하시겠어요?"
        ),
        _AXIS_UX: "환자·보호자 등 IT 에 익숙하지 않은 사용자도 써야 한다면, 무엇을 고려하시겠어요?",
    },
    "mobility": {
        _AXIS_PRIVACY: (
            "위치 정보처럼 실시간 민감 데이터를 수집해야 한다면, 보관 기간이나 동의 범위를 "
            "어떻게 정하시겠어요?"
        ),
        _AXIS_RELIABILITY: (
            "실시간 위치·경로 처리 중 일부 데이터가 유실되거나 지연된다면, 어떻게 대응하시겠어요?"
        ),
        _AXIS_UX: (
            "이동 중(네트워크 불안정 등) 사용자가 지연을 겪는 상황이라면, 체감 지연을 어떻게 "
            "줄이시겠어요?"
        ),
    },
    "etc": {
        _AXIS_PRIVACY: (
            "서비스에서 다루는 사용자 데이터 중 어떤 항목을 민감하다고 판단하고, 어떻게 "
            "보호하시겠어요?"
        ),
        _AXIS_RELIABILITY: "장애나 예외 상황이 발생한다면, 어떻게 감지하고 대응하시겠어요?",
        _AXIS_UX: "실제 사용자 피드백이나 사용 맥락이 주어진다면, 무엇을 우선 개선하시겠어요?",
    },
}

DOMAIN_QUESTION_FRAMES: tuple[DomainQuestionFrameSpec, ...] = tuple(
    DomainQuestionFrameSpec(domain_category=domain, axis=axis, frame_text=text_)
    for domain in DOMAIN_CATEGORIES
    for axis, text_ in _FRAME_TEXT_BY_DOMAIN[domain].items()
)


async def seed_domain_question_frames(
    session: AsyncSession,
    frames: Iterable[DomainQuestionFrameSpec] = DOMAIN_QUESTION_FRAMES,
) -> None:
    """domain_question_frames 를 upsert 한다. display_order 는 axis 당 1개라 고정 1이다.

    재실행해도 같은 결과다(idempotent) — frame_text 는 팀 검수에 따라 갱신될 수 있어
    존재하는 행이라도 값이 다르면 덮어쓴다.

    문구는 독립·도메인·한국어 검수 전 개발 후보다(spec/ai/decisions/0005, 0008). 그래서
    is_active=FALSE 로 넣고, 충돌 시에도 is_active 는 건드리지 않는다. 검수가 끝난 뒤
    운영에서 활성화한 값을 재시드가 되돌리지 않는다.
    """
    for frame in frames:
        await session.execute(
            text(
                """
                INSERT INTO domain_question_frames
                    (domain_category, axis, frame_text, display_order, is_active)
                VALUES
                    (:domain_category, :axis, :frame_text, 1, FALSE)
                ON CONFLICT (domain_category, axis, display_order) DO UPDATE SET
                    frame_text = EXCLUDED.frame_text,
                    updated_at = now()
                """
            ),
            {
                "domain_category": frame.domain_category,
                "axis": frame.axis,
                "frame_text": frame.frame_text,
            },
        )


__all__ = ["DOMAIN_QUESTION_FRAMES", "DomainQuestionFrameSpec", "seed_domain_question_frames"]
