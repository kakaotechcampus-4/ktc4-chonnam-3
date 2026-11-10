"""profile_summary 갱신: 완료 면접 저장소 집계 + 개인 역할 요약.

언어·유형·저장소 수는 기존 자료로만 계산하고 LLM 은 role_summary 하나만 만든다.
완료 면접·실제 입력·활성 프롬프트의 지문이 같으면 역할 요약을 재사용한다.
실패하면 어떤 값도 쓰지 않아 이전 성공 요약이 그대로 남는다. 이 job 의 실패는 report 와 무관하다.

docs/task-16-report.md / ADR 0016·0019
"""

import hashlib
import json
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from functools import partial
from typing import Literal, cast

import httpx
from devon_ai import contracts as c
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import LLMSettings
from app.db.models import Repository, User, UserProfileSummary
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
type LoadGenerated = Callable[[str], Awaitable[dict[str, object] | None]]
type PreserveGenerated = Callable[[dict[str, object]], Awaitable[bool]]


async def _profile_input(
    db: AsyncSession,
    user_id: uuid.UUID,
    llm: LLMSettings,
) -> tuple[dict[str, object], dict[str, object], list[str], c.PromptSpec, str] | None:
    repos = await queries.completed_interview_repositories(db, user_id=user_id)
    if not repos:
        return None
    ids = tasks.based_repo_ids(repo.id for repo in repos)
    by_id = {repo.id: repo for repo in repos}
    languages = tasks.aggregate_languages({identity: by_id[identity].languages for identity in ids})
    shallow = await queries.shallow_results(db, repo_ids=ids)
    types_by_repo = {identity: _project_types(shallow.get(identity)) for identity in ids}
    project_types = tasks.aggregate_project_types(types_by_repo)
    values: dict[str, object] = {
        "based_repo_ids": ids,
        "based_on_repo_count": len(ids),
        "languages": languages,
        "project_types": project_types,
    }
    prompt = await load_active_prompt(db, PROFILE_PROMPT_TASK)
    payload, statements = await _role_payload(
        db,
        user_id=user_id,
        repos=[by_id[identity] for identity in ids],
        types_by_repo=types_by_repo,
        statistics={
            "based_on_repo_count": len(ids),
            "languages": languages,
            "project_types": project_types,
        },
    )
    versions = await queries.completed_versions(db, user_id=user_id, repo_ids=ids)
    task_limits = llm.call_limits(prompt.task_name)
    encoded = json.dumps(
        {
            "payload": payload,
            # 보고서 재평가 회차는 outbox가 감사 기록으로 보존한다.
            # 모델 입력이 같으면 재과금하지 않는다.
            "sources": [
                {key: value for key, value in row.items() if key != "report_revision"}
                for row in versions
            ],
            "repo_ids": [str(i) for i in ids],
            "prompt": asdict(prompt),
            "generation": {
                "reasoning_effort": task_limits.reasoning_effort,
                "max_output_tokens": task_limits.max_output_tokens,
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
    values["input_fingerprint"] = fingerprint
    return values, payload, statements, prompt, fingerprint


async def refresh_profile_summary(
    sessions: async_sessionmaker[AsyncSession],
    *,
    user_id: uuid.UUID,
    llm: LLMSettings,
    http_client: httpx.AsyncClient | None,
    generator: RoleGenerator | None = None,
    check_current: Callable[[], Awaitable[bool]] | None = None,
    load_generated: LoadGenerated | None = None,
    preserve_generated: PreserveGenerated | None = None,
) -> RefreshOutcome:
    """완료 면접·실제 입력·프롬프트가 같을 때만 재사용하고 저장 직전에 다시 확인한다."""
    async with sessions.begin() as db:
        # 기존 user-only job과 직접 호출도 원문 조회·모델 실행 전에 검사한다.
        user = await db.get(User, user_id)
        if user is None or user.status != "active":
            return "skipped"
        source = await _profile_input(db, user_id, llm)
        if source is None:
            return "skipped"
        values, payload, statements, prompt, fingerprint = source
        previous = await queries.get_summary(db, user_id=user_id)
        if _can_reuse_role(previous, fingerprint):
            # 재사용도 쓰기 작업이다. 짧은 저장 트랜잭션에서 철회와 순서를 맞춘다.
            user = await db.get(User, user_id, with_for_update=True, populate_existing=True)
            if user is None or user.status != "active":
                return "skipped"
            if check_current is not None and not await check_current():
                return "skipped"
            await queries.save_summary(
                db, user_id=user_id, values=values, generated_at=datetime.now(UTC)
            )
            return "role_kept"
    if not statements:
        raise tasks.RoleEvidenceMissingError("no statements")
    generated = await load_generated(fingerprint) if load_generated is not None else None
    if generated is None:
        metadata: list[c.AttemptMetadata] = []
        model_call = cast(
            ModelCall,
            partial(
                call_model,
                api_key=llm.openai_api_key,
                base_url=llm.llm_base_url,
                http_client=http_client,
                budget=CallBudget(),
                attempt_sink=metadata,
            ),
        )
        role_summary = await (generator or tasks.generate_role_summary)(
            payload,
            prompt=prompt,
            limits=llm.call_limits(prompt.task_name),
            model_call=model_call,
            statements=statements,
        )
        generated = {
            "fingerprint": fingerprint,
            "role_summary": tasks.validate_role_summary({"role_summary": role_summary}, statements),
            "model": metadata[-1].model if metadata else prompt.model,
            "prompt_version": prompt.version,
            "generation_limits": asdict(llm.call_limits(prompt.task_name)),
        }
        if preserve_generated is not None and not await preserve_generated(generated):
            return "skipped"
    generated_values = _generated_values(generated, fingerprint, statements, prompt)
    async with sessions.begin() as db:
        # 실행권과 원문 버전을 모두 검사해 오래된 요약이 새 입력 결과를 덮어쓰지 않게 한다.
        user = await db.get(User, user_id, with_for_update=True)
        if user is None or user.status != "active":
            return "skipped"
        if check_current is not None and not await check_current():
            return "skipped"
        current = await _profile_input(db, user_id, llm)
        if current is None or current[-1] != fingerprint:
            return "skipped"
        await queries.save_summary(
            db,
            user_id=user_id,
            values=values | generated_values,
            generated_at=datetime.now(UTC),
        )
    return "updated"


def _generated_values(
    saved: dict[str, object], fingerprint: str, statements: list[str], prompt: c.PromptSpec
) -> dict[str, object]:
    if (
        saved.get("fingerprint") != fingerprint
        or saved.get("prompt_version") != prompt.version
        or not isinstance(saved.get("model"), str)
        or not str(saved["model"]).strip()
    ):
        raise tasks.RoleSummaryInvalidError("invalid generation provenance")
    role = tasks.validate_role_summary({"role_summary": saved.get("role_summary")}, statements)
    limits = TypeAdapter(c.CallLimits).validate_python(saved.get("generation_limits"))
    # 저장 당시 실행 정보는 보존한다. 재사용 때 바뀐 timeout으로 과거 생성을 다시 표기하지 않는다.
    return {
        "role_summary": role,
        "model": saved["model"],
        "prompt_version": prompt.version,
        "generation_limits": asdict(limits),
    }


def _can_reuse_role(previous: UserProfileSummary | None, fingerprint: str) -> bool:
    return (
        previous is not None
        and bool(previous.role_summary)
        and (previous.input_fingerprint == fingerprint)
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
