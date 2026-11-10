"""준비 큐→실제 WS 9턴→리포트 큐→프로필 큐를 한 사용자의 DB로 검증한다.

모델과 GitHub의 네트워크만 HTTP 대역이다. 서비스·AI 계약·ARQ 실행·저장은 대체하지 않는다.
"""

import asyncio
import importlib
import json
from dataclasses import asdict

import pytest
from arq.worker import Worker
from redis.asyncio import Redis
from sqlalchemy import select

from app.core import config as config_module
from app.db.models import (
    Evidence,
    InterviewReport,
    InterviewSession,
    InterviewTurn,
    LLMCallRecord,
    PromptVersion,
    ReportScore,
    Repository,
    ScoreCriterion,
    UserProfileSummary,
)
from app.db.models.report import SCORE_KEYS
from app.workers.tasks import profile_summary, report_generate
from tests.agents import test_director_prepare, test_director_ws
from tests.agents.director_helpers import analysis, approved_review, plan, response
from tests.features.report.factories import sample_rubric
from tests.features.report.test_report_ai_contract import _narrative_output

ready = test_director_prepare.ready
connect_ws = test_director_ws.connect_ws


@pytest.fixture
async def isolated_flow_queue(test_redis_url):
    redis = Redis.from_url(test_redis_url)
    await redis.flushdb()
    try:
        yield
    finally:
        await redis.flushdb()
        await redis.aclose()


class FlowProvider:
    def __init__(self, seed, sessions):
        self.github, self.sessions = test_director_prepare.Transport(seed), sessions
        self.calls = []
        self.report_turns = []

    async def __call__(self, request):
        if request.method != "POST":
            return await self.github(request)
        body = json.loads(request.content)
        name = body["text"]["format"]["name"]
        payload = json.loads(body["input"][0]["content"][0]["text"])
        self.calls.append(name)
        # 모델 응답 대기 중에도 별도 DB 연결에서 면접 행을 잠글 수 있어야 한다.
        async with self.sessions.begin() as db:
            await db.scalar(select(InterviewSession).with_for_update())
        if payload.get("operation") == "plan":
            return response(plan(payload["context"]["allowed_personas"][0]))
        if payload.get("operation") == "review":
            return response(approved_review())
        if name == "AnswerAnalysis":
            return response(asdict(analysis()))
        if name == "ScoreJudgments":
            self.report_turns = payload["turns"]
            return response(
                {
                    "judgments": [
                        {"turn_id": turn["turn_id"], "key": key, "level": 3}
                        for turn in payload["turns"]
                        for key in turn["candidate_keys"]
                    ]
                }
            )
        if name == "ReportNarrative":
            assert len(payload["turns"]) == 9
            return response(_narrative_output())
        if name == "ProfileRoleSummary":
            assert len(payload["interview_statements"]) == 9
            return response({"role_summary": "팀원 담당이라고 면접에서 설명했습니다."})
        raise AssertionError(f"예상하지 않은 모의 모델 계약: {name}")


async def _run_registered_jobs(app, functions, count):
    # 실제 등록 함수를 ARQ가 Redis 큐에서 꺼내 실행하며 후속 enqueue까지 검사한다.
    async with asyncio.timeout(60):
        for _ in range(count):
            worker = Worker(
                functions=functions,
                redis_pool=app.state.redis,
                burst=True,
                handle_signals=False,
                ctx={
                    "settings": app.state.settings,
                    "session_factory": app.state.session_factory,
                    "http_client": app.state.http_client,
                },
                max_jobs=1,
                max_tries=1,
                max_burst_jobs=1,
                poll_delay=0.01,
                job_timeout=30,
            )
            # burst는 실행 중 후속 enqueue보다 먼저 종료를 정할 수 있어 다음 poll을 분리한다.
            assert await worker.run_check() == 1


async def test_preparation_nine_answers_report_and_profile_share_one_real_flow(
    agent_sessions, ready, connect_ws, monkeypatch, isolated_flow_queue
):
    seed = ready
    async with agent_sessions.begin() as db:
        repo = await db.get(Repository, seed["repo_id"])
        repo.languages = {"Python": 100}
        for criterion in await db.scalars(select(ScoreCriterion)):
            criterion.rubric = sample_rubric(criterion.score_key)
        db.add_all(
            PromptVersion(
                task_name=task,
                version="flow-v1",
                model="flow-model",
                template="fixture",
                is_active=True,
            )
            for task in ("report", "report_score", "profile_summary")
        )
    provider = FlowProvider(seed, agent_sessions)

    with connect_ws(provider) as (client, app, path, _, _):
        # 실제 WorkerSettings 등록은 유지하고 설정·외부 HTTP 자원만 테스트 것으로 주입한다.
        monkeypatch.setattr(config_module, "get_settings", lambda: app.state.settings)
        monkeypatch.setattr(report_generate, "get_settings", lambda: app.state.settings)
        monkeypatch.setattr(profile_summary, "get_settings", lambda: app.state.settings)
        registered = importlib.import_module("app.workers.arq_app").WorkerSettings.functions
        assert {"interview_prep", "report_generate", "profile_summary"} <= {
            getattr(item, "coroutine", item).__name__ for item in registered
        }

        async def enqueue_preparation():
            await app.state.redis.enqueue_job("interview_prep", str(seed["interview_id"]))

        with client.websocket_connect(path, headers={"origin": "http://localhost:5173"}) as socket:
            client.portal.call(enqueue_preparation)
            client.portal.call(_run_registered_jobs, app, registered, 1)
            preparation = []
            while True:
                event = socket.receive_json()
                assert event["type"] != "error", event
                preparation.append(event)
                if event["type"] == "question":
                    assert event["turn"] == 1 and event["persona"] == "hr_manager"
                    break
            assert {"type": "prepareCompleted"} in preparation

            for number in range(1, 10):
                socket.send_json({"type": "answer", "turn": number, "text": "팀원 담당입니다"})
                assert socket.receive_json() == {"type": "answerReceived"}
                assert socket.receive_json() == {"type": "thinking"}
                event = socket.receive_json()
                if number == 9:
                    assert event == {"type": "interviewEnd"}
                else:
                    assert event["type"] == "question" and event["turn"] == number + 1

        detail = client.get(f"/api/interviews/{seed['interview_id']}")
        assert detail.status_code == 200 and detail.json()["status"] == "completed"
        assert len(detail.json()["turns"]) == 9
        report_path = f"/api/interviews/{seed['interview_id']}/report"
        assert client.get(report_path).status_code == 202
        client.portal.call(_run_registered_jobs, app, registered, 2)
        report = client.get(report_path)
        assert report.status_code == 200, report.text
        assert len(report.json()["turns"]) == 9
        assert {item["key"] for item in report.json()["scores"]} == set(SCORE_KEYS)

    async with agent_sessions() as db:
        interview = await db.get(InterviewSession, seed["interview_id"])
        turns = list(await db.scalars(select(InterviewTurn).order_by(InterviewTurn.turn_no)))
        assert interview.status == "completed" and interview.completed_at is not None
        assert [step["status"] for step in interview.prepare_steps] == ["completed"] * 4
        assert len(turns) == 9
        assert all(turn.answer_text == "팀원 담당입니다" and turn.analysis for turn in turns)
        assert await db.scalar(select(Evidence.id)) is not None
        assert await db.scalar(select(InterviewReport.id)) is not None
        assert len(list(await db.scalars(select(ReportScore)))) == 6
        profile = await db.scalar(select(UserProfileSummary))
        assert profile.based_repo_ids == [seed["repo_id"]]
        assert profile.languages == [{"name": "Python", "ratio": 100.0}]
        assert profile.role_summary == "팀원 담당이라고 면접에서 설명했습니다."
        records = list(await db.scalars(select(LLMCallRecord)))
        assert records and all(record.failure is None for record in records)
    assert provider.calls.count("AnswerAnalysis") == 9
    assert provider.calls.count("ScoreJudgments") == 1
    assert provider.calls.count("ReportNarrative") == 1
    assert provider.calls.count("ProfileRoleSummary") == 1
    assert len(provider.report_turns) == 9
    assert provider.github.github
