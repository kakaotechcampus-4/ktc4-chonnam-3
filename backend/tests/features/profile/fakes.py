"""profile_summary 테스트 공용 대역·helper. 실제 LLM 은 호출하지 않는다. task-16"""

from sqlalchemy import select

from app.core.config import LLMSettings
from app.db.models import UserProfileSummary
from app.features.profile import service

from ..interview.factories import make_interview, make_turn

LLM = LLMSettings(
    openai_api_key="k",
    llm_default_model="m",
    llm_timeout_seconds=5,
    llm_max_output_tokens=100,
    llm_max_input_bytes=100000,
    llm_max_response_bytes=100000,
)
ROLE = "인증 API 를 만들었다고 면접에서 설명했습니다."


class FakeGenerator:
    """generate_role_summary 대역. 호출 횟수와 받은 인자를 기록한다."""

    def __init__(self, text=ROLE, error=None):
        self.text, self.error, self.calls = text, error, []

    async def __call__(self, payload, *, prompt, limits, model_call, statements):
        self.calls.append((payload, list(statements)))
        if self.error:
            raise self.error
        return self.text


async def completed_interview(db, run, repos, *, status="completed", answered=True):
    interview = await make_interview(db, run, repos, status=status)
    await make_turn(db, interview, 1, answered=answered, answer_text="인증 API 를 만들었습니다.")
    await db.commit()
    return interview


async def read_summary(db, user):
    return await db.scalar(
        select(UserProfileSummary)
        .where(UserProfileSummary.user_id == user.id)
        .execution_options(populate_existing=True)
    )


async def refresh_summary(app, user, generator):
    return await service.refresh_profile_summary(
        app.state.session_factory, user_id=user.id, llm=LLM, http_client=None, generator=generator
    )
