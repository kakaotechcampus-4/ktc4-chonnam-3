"""profile_summary 갱신: 완료 면접 저장소 집계 + 개인 역할 요약.

언어·유형·저장소 수는 기존 자료로만 계산하고 LLM 은 role_summary 하나만 만든다.
입력 저장소 집합이 저장된 based_repo_ids 와 같으면 역할 요약은 다시 만들지 않는다.
실패하면 어떤 값도 쓰지 않아 이전 성공 요약이 그대로 남는다. 이 job 의 실패는 report 와 무관하다.

docs/task-16-report.md / ADR 0016·0019
"""

import uuid
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from functools import partial
from typing import Literal, cast

import httpx
from devon_ai import contracts as c
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import LLMSettings
from app.db.models import Repository, UserProfileSummary
from app.features.profile import queries
from app.integrations.llm.client import CallBudget, call_model
from app.llm_tasks import profile_summary as tasks
from app.llm_tasks.prompt_loader import (
    PromptConfigurationError,
    PromptNotFoundError,
    load_active_prompt,
)
from app.llm_tasks.report import ModelCall

PROFILE_PROMPT_TASK = "profile_summary"
# docs/redis-keys.md: profile summary lock
PROFILE_LOCK_KEY = "profile:gen:{user_id}"
PROFILE_LOCK_TTL_SECONDS = 10 * 60
STATEMENT_TURN_LIMIT = 40
ANSWER_MAX_CHARS = 1500

type RoleGenerator = Callable[..., Awaitable[str]]
type RefreshOutcome = Literal["updated", "role_kept", "skipped"]


async def refresh_profile_summary(
    sessions: async_sessionmaker[AsyncSession],
    *,
    user_id: uuid.UUID,
    llm: LLMSettings,
    http_client: httpx.AsyncClient | None,
    generator: RoleGenerator | None = None,
) -> RefreshOutcome:
    """집계를 저장한다. 대상 저장소가 없으면 "skipped", 역할 요약을 재사용하면 "role_kept".

    DB transaction 은 입력 수집과 저장에 각각 짧게만 쓰고 모델 호출 중에는 열어 두지 않는다.
    실패는 예외로 전파하며 호출자(worker)가 로그와 lock 을 맡는다.
    """
    async with sessions.begin() as db:
        repos = await queries.completed_interview_repositories(db, user_id=user_id)
        if not repos:
            return "skipped"
        ids = tasks.based_repo_ids(repo.id for repo in repos)
        by_id = {repo.id: repo for repo in repos}
        # 언어 자료 누락은 여기서 실패한다. 모델을 부르기 전이라 호출 비용도 없다.
        languages = tasks.aggregate_languages({i: by_id[i].languages for i in ids})
        shallow = await queries.shallow_results(db, repo_ids=ids)
        types_by_repo = {i: _project_types(shallow.get(i)) for i in ids}
        project_types = tasks.aggregate_project_types(types_by_repo)
        previous = await queries.get_summary(db, user_id=user_id)
        values: dict[str, object] = {
            "based_repo_ids": ids,
            "based_on_repo_count": len(ids),
            "languages": languages,
            "project_types": project_types,
        }
        if _can_reuse_role(previous, ids):
            await queries.save_summary(
                db, user_id=user_id, values=values, generated_at=datetime.now(UTC)
            )
            return "role_kept"
        prompt = await load_active_prompt(db, PROFILE_PROMPT_TASK)
        payload, statements = await _role_payload(
            db,
            user_id=user_id,
            repos=[by_id[i] for i in ids],
            types_by_repo=types_by_repo,
            statistics={
                "based_on_repo_count": len(ids),
                "languages": languages,
                "project_types": project_types,
            },
        )
    if not statements:
        raise tasks.RoleEvidenceMissingError("no statements")

    generate = generator or tasks.generate_role_summary
    model_call = cast(
        ModelCall,
        partial(
            call_model,
            api_key=llm.openai_api_key,
            base_url=llm.llm_base_url,
            http_client=http_client,
            budget=CallBudget(),
        ),
    )
    role_summary = await generate(
        payload,
        prompt=prompt,
        limits=llm.call_limits(),
        model_call=model_call,
        statements=statements,
    )
    async with sessions.begin() as db:
        await queries.save_summary(
            db,
            user_id=user_id,
            values=values
            | {
                "role_summary": role_summary,
                "model": prompt.model,
                "prompt_version": prompt.version,
            },
            generated_at=datetime.now(UTC),
        )
    return "updated"


def _can_reuse_role(previous: UserProfileSummary | None, ids: list[uuid.UUID]) -> bool:
    return (
        previous is not None
        and bool(previous.role_summary)
        and list(previous.based_repo_ids) == ids
    )


def _project_types(result: Mapping[str, object] | None) -> list[str]:
    """L1 결과에서 project_types 만 꺼낸다. 읽을 수 없는 결과는 유형 없음으로 둔다."""
    if result is None:
        return []
    try:
        return list(c.decode(c.ShallowRepoAnalysis, result).project_types)
    except c.ContractError:
        return []


async def _role_payload(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    repos: list[Repository],
    types_by_repo: Mapping[uuid.UUID, list[str]],
    statistics: dict[str, object],
) -> tuple[dict[str, object], list[str]]:
    """모델 입력과 그 안에 담은 진술 원문. 프로젝트 설명(facts)과 면접 답변(statements)을 나눈다."""
    ids = [repo.id for repo in repos]
    turns = await queries.answered_turns(
        db, user_id=user_id, repo_ids=ids, limit=STATEMENT_TURN_LIMIT
    )
    names = await queries.interview_repository_names(
        db, interview_ids=list({interview_id for interview_id, _ in turns}), repo_ids=ids
    )
    statements = [
        {
            "repositories": names.get(interview_id, []),
            "persona": turn.persona,
            "turn_no": turn.turn_no,
            "question": turn.question_text,
            "answer": (turn.answer_text or "")[:ANSWER_MAX_CHARS],
        }
        for interview_id, turn in turns
    ]
    payload: dict[str, object] = {
        "statistics": statistics,
        "repository_facts": [
            {
                "name": repo.name,
                "description": repo.description,
                "project_types": types_by_repo[repo.id],
                "commit_count": repo.commit_count,
                "user_commit_count": repo.user_commit_count,
            }
            for repo in repos
        ],
        "interview_statements": statements,
    }
    return payload, [str(item["answer"]) for item in statements if item["answer"]]


def failure_code(error: BaseException) -> str:
    """로그에 남길 실패 코드. 원문 예외 메시지·LLM 출력은 남기지 않는다."""
    if isinstance(error, tasks.ProfileSummaryError):
        return error.code
    if isinstance(error, PromptNotFoundError | PromptConfigurationError):
        return "prompt_unavailable"
    if isinstance(error, c.ContractError):
        return "llm_failed"
    return "internal_error"
