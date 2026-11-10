"""실제 서비스의 공고 저장·준비·9턴·리포트 작업을 연결하는 회귀 도우미."""

from dataclasses import asdict
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import (
    AnalysisJob,
    AnalysisRepoCandidate,
    DomainQuestionFrame,
    InterviewSession,
    JdRequirement,
    PromptVersion,
    RepoAnalysis,
    Repository,
)
from app.features.analysis.posting_service import get_or_fetch_posting
from app.features.interview.director_service import process_answer
from app.features.interview.prepare import prepare_interview
from app.workers.tasks import report_generate
from tests.agents.test_director_prepare import area, deep, shallow
from tests.features.interview.factories import make_user
from tests.features.report.factories import seed_criteria

from .image_jd_lineage_provider import ANSWER, URL, ImageLineageProvider


def settings():
    return Settings(
        _env_file=None,
        openai_api_key="fixture",
        llm_default_model="fixture",
        llm_timeout_seconds=5,
        llm_max_output_tokens=4096,
        llm_max_input_bytes=262144,
        llm_max_response_bytes=262144,
        vision_base_url="https://vision.example",
        vision_api_key="fixture",
    )


async def initialize(app, client, monkeypatch, *, excerpt=False, prepare_session=True):
    provider = ImageLineageProvider(excerpt=excerpt)
    provider.settings = settings().require_vision()
    monkeypatch.setattr("app.integrations.jd.images.EliceVisionClient", lambda config: provider)
    monkeypatch.setattr(report_generate, "get_settings", settings)
    sessions = app.state.session_factory
    async with sessions.begin() as db:
        for task, version in (
            ("jd_extract_image", "jd_extract_image_v1"),
            ("director", "director_v8"),
            ("answer_analysis", "answer_analysis_v5"),
            ("repo_deep", "repo_deep_v1"),
            ("report", "report_v3"),
            ("report_score", "report_score_v3"),
        ):
            db.add(
                PromptVersion(
                    task_name=task,
                    version=version,
                    model="fixture",
                    template="합성 HTTP 회귀 응답용 프롬프트",
                    is_active=True,
                )
            )
        await seed_criteria(db)
        db.add(
            DomainQuestionFrame(
                domain_category="etc",
                axis="reliability_operations",
                frame_text="실패를 어떻게 관찰하고 복구하나요?",
                is_active=True,
            )
        )
    http = httpx.AsyncClient(transport=httpx.MockTransport(provider))
    try:
        posting = await get_or_fetch_posting(sessions, URL, client=http, settings=settings())
        async with sessions.begin() as db:
            owner = await make_user(db)
            run = AnalysisJob(
                user_id=owner.id,
                job_type="analysis_run",
                status="succeeded",
                job_posting_id=posting.id,
            )
            repo = Repository(
                user_id=owner.id,
                github_repo_id=123,
                name="sample",
                full_name="owner/sample",
                head_sha="a" * 40,
            )
            db.add_all([run, repo])
            await db.flush()
            seed = {"owner": owner.id, "repo_id": repo.id, "sha": repo.head_sha}
            l1 = RepoAnalysis(
                repository_id=repo.id,
                analysis_level="l1",
                head_sha=repo.head_sha,
                prompt_version="repo_shallow_v3",
                model="fixture",
                status="succeeded",
                result=asdict(shallow(seed)),
            )
            db.add(l1)
            await db.flush()
            db.add(
                AnalysisRepoCandidate(
                    analysis_job_id=run.id,
                    repository_id=repo.id,
                    base_rank=1,
                    batch_no=1,
                    batch_rank=1,
                    filter_status="eligible",
                    ranking_signals={
                        "analysis": {
                            "analysis_id": str(l1.id),
                            "status": "succeeded",
                            "head_sha": l1.head_sha,
                            "prompt_version": l1.prompt_version,
                        }
                    },
                )
            )
            db.add(
                RepoAnalysis(
                    repository_id=repo.id,
                    analysis_level="l2",
                    head_sha=repo.head_sha,
                    prompt_version="repo_deep_v1",
                    model="fixture",
                    status="succeeded",
                    notable_areas=[area()],
                    result={"analysis": deep(seed), "rejected_areas": []},
                )
            )
            requirements = list(
                await db.scalars(
                    select(JdRequirement)
                    .where(JdRequirement.job_posting_id == posting.id)
                    .order_by(JdRequirement.display_order)
                )
            )
        provider.bind_repository(seed)
        client.cookies.set("devon_session", await app.state.sessions.create(owner.id))
        created = await client.post(
            "/api/interviews", json={"runId": str(run.id), "repositoryIds": [str(repo.id)]}
        )
        assert created.status_code == 201, created.text
        iid = UUID(created.json()["interviewId"])
        if prepare_session:
            prepared = await prepare_interview(
                sessions, user_id=owner.id, interview_id=iid, settings=settings(), http_client=http
            )
            async with sessions() as db:
                state = await db.get(InterviewSession, iid)
                assert prepared, state.last_error
        return dict(
            provider=provider,
            http=http,
            posting=posting,
            owner=owner.id,
            interview=iid,
            requirements=requirements,
        )
    except BaseException:
        await http.aclose()
        raise


async def finish_interview(app, scenario):
    # 음성 세션의 확정 전사 이후 공통 경로를 실행한다. STT·WS·실제 마이크 검증은 아니다.
    for number in range(1, 10):
        result = await process_answer(
            app.state.session_factory,
            user_id=scenario["owner"],
            interview_id=scenario["interview"],
            turn_no=number,
            text=ANSWER,
            call_id=uuid4(),
            settings=settings().require_llm(),
            http_client=scenario["http"],
        )
        assert result.accepted and result.failure is None, result
        assert result.completed is (number == 9)
    async with app.state.session_factory() as db:
        interview = await db.get(InterviewSession, scenario["interview"])
        assert interview.status == "completed" and interview.current_turn == 9


async def generate_report(app, client, scenario):
    path = f"/api/interviews/{scenario['interview']}/report"
    pending = await client.get(path)
    assert pending.status_code == 202, pending.text
    await report_generate.report_generate(
        {
            "session_factory": app.state.session_factory,
            "redis": app.state.redis,
            "http_client": scenario["http"],
        },
        str(scenario["interview"]),
    )
    report = await client.get(path)
    assert report.status_code == 200, report.text
    return report.json()
