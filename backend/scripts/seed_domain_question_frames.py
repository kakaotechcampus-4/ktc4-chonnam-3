"""domain_question_frames 시드. domain_category × axis 조합마다 질문 뼈대 1개(총 21개).

docs/db-schema.md · task-03 근거: spec/backend/features/interview.md

domain_lead 페르소나가 이 frame_text 를 참고해 도메인 관점 질문을 구성한다.
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
        _AXIS_PRIVACY: "계좌·거래 내역처럼 민감한 금융 정보를 다룰 때 접근 권한이나 로그 노출을 "
        "어떻게 제한했는지 물어본다.",
        _AXIS_RELIABILITY: "결제·정산처럼 실패가 금전적 손실로 이어지는 흐름에서 장애 상황을 "
        "어떻게 감지하고 복구했는지 물어본다.",
        _AXIS_UX: "잔액·거래 결과처럼 숫자 하나의 오차도 신뢰를 깨는 화면에서 사용자에게 "
        "상태를 어떻게 명확히 전달했는지 물어본다.",
    },
    "game": {
        _AXIS_PRIVACY: "유저 계정·결제 정보와 플레이 로그를 함께 다룰 때 개인 식별 정보를 "
        "어떻게 분리해서 취급했는지 물어본다.",
        _AXIS_RELIABILITY: "동시 접속이 몰리는 순간(이벤트·업데이트 직후)에 서버가 버티도록 "
        "무엇을 고려했는지 물어본다.",
        _AXIS_UX: "입력 지연이나 프레임 저하가 체감에 바로 드러나는 상황에서 사용자 경험을 "
        "어떻게 확인하고 개선했는지 물어본다.",
    },
    "travel": {
        _AXIS_PRIVACY: "예약자 개인정보와 결제·여권 정보를 외부 API 로 넘길 때 어떤 기준으로 "
        "최소한만 전달했는지 물어본다.",
        _AXIS_RELIABILITY: "외부 항공/숙박 API 가 지연되거나 실패할 때 예약 흐름을 어떻게 "
        "안전하게 처리했는지 물어본다.",
        _AXIS_UX: "여러 단계를 거치는 예약 과정에서 사용자가 진행 상태를 어떻게 파악할 수 "
        "있게 했는지 물어본다.",
    },
    "shopping": {
        _AXIS_PRIVACY: "주문·배송 정보 같은 개인정보가 여러 서비스(결제·물류)로 흘러갈 때 "
        "어떻게 보호했는지 물어본다.",
        _AXIS_RELIABILITY: "특가·할인 이벤트로 트래픽이 급증할 때 재고·주문 정합성을 어떻게 "
        "지켰는지 물어본다.",
        _AXIS_UX: "장바구니·결제처럼 이탈이 잦은 구간에서 사용자 편의를 어떻게 개선했는지 "
        "물어본다.",
    },
    "medical": {
        _AXIS_PRIVACY: "진료·건강 정보 같은 민감정보를 다룰 때 접근 통제나 익명화를 어떻게 "
        "적용했는지 물어본다.",
        _AXIS_RELIABILITY: "예약·처방처럼 실수가 안전 문제로 이어질 수 있는 기능에서 검증을 "
        "어떻게 강화했는지 물어본다.",
        _AXIS_UX: "환자·보호자 등 IT 에 익숙하지 않은 사용자도 쓸 수 있도록 무엇을 고려했는지 "
        "물어본다.",
    },
    "mobility": {
        _AXIS_PRIVACY: "위치 정보처럼 실시간 민감 데이터를 수집할 때 보관 기간이나 동의 범위를 "
        "어떻게 다뤘는지 물어본다.",
        _AXIS_RELIABILITY: "실시간 위치·경로 처리 중 일부 데이터가 유실되거나 지연될 때 어떻게 "
        "대응했는지 물어본다.",
        _AXIS_UX: "이동 중(네트워크 불안정 등) 사용자가 겪는 지연을 어떻게 체감상 줄였는지 "
        "물어본다.",
    },
    "etc": {
        _AXIS_PRIVACY: "서비스에서 다루는 사용자 데이터 중 민감하다고 판단한 항목과 그 보호 "
        "방법을 물어본다.",
        _AXIS_RELIABILITY: "장애나 예외 상황이 발생했을 때 어떻게 감지하고 대응했는지 물어본다.",
        _AXIS_UX: "실제 사용자 피드백이나 사용 맥락을 반영해 무엇을 개선했는지 물어본다.",
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
    """
    for frame in frames:
        await session.execute(
            text(
                """
                INSERT INTO domain_question_frames
                    (domain_category, axis, frame_text, display_order, is_active)
                VALUES
                    (:domain_category, :axis, :frame_text, 1, TRUE)
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
