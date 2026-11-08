from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.features.interview import ws
from app.features.interview.question_replay import ExplicitReplayCommands


@pytest.mark.parametrize(
    "text",
    [
        "다시 말씀해 주세요.",
        "질문을 다시 말씀해 주세요",
        "방금 질문을 한 번 더 들려주세요.",
        "죄송하지만 질문을 다시 읽어 주세요.",
    ],
)
def test_explicit_whole_request_is_replay(text):
    assert ExplicitReplayCommands().is_explicit(text)


@pytest.mark.parametrize(
    "text",
    [
        "모르겠습니다",
        "잘 모르겠습니다. 다시 설명하는 기능을 구현했습니다.",
        "'다시 말씀해 주세요'라는 버튼을 만들었습니다.",
        "다시 말씀해 주세요라는 문장은 요청입니다",
        "다시 Redis에 저장하면 됩니다.",
        "답변을 다시 말씀해 주세요",
        "질문을 다시 설명한 이유는 사용성입니다.",
    ],
)
def test_answers_and_quoted_commands_are_preserved(text):
    assert not ExplicitReplayCommands().is_explicit(text)


@pytest.mark.asyncio
async def test_replay_resends_same_question_without_answer_execution(monkeypatch):
    question = {"type": "question", "turn": 2, "text": "기술 질문", "audioUrl": "/audio"}
    state = ws._State("in_progress", question, {"currentTurn": 2}, None, ())

    async def read(*args):
        return state

    monkeypatch.setattr(ws, "_read_state", read)

    async def forbidden(*args):
        raise AssertionError("Replay must not save or analyze an answer")

    monkeypatch.setattr(ws, "_execute", forbidden)
    events = []

    class Connection:
        interview_id = uuid4()
        socket = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

        async def send(self, event):
            events.append(event)

    assert await ws._run_answer(
        Connection(), uuid4(), 2, "질문을 다시 말씀해 주세요", "answer_rejected"
    )
    assert events == [question]


@pytest.mark.asyncio
async def test_dont_know_remains_normal_answer(monkeypatch):
    state = ws._State(
        "in_progress",
        {"type": "question", "turn": 2, "text": "기술 질문"},
        {"currentTurn": 2},
        None,
        (),
    )

    async def read(*args):
        return state

    monkeypatch.setattr(ws, "_read_state", read)
    answers = []

    async def execute(connection, user_id, turn, text):
        answers.append((turn, text))
        return SimpleNamespace(failure=None, discard_reason=None)

    monkeypatch.setattr(ws, "_execute", execute)

    class Connection:
        interview_id = uuid4()
        socket = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

        async def restore(self, user_id):
            return True

    assert await ws._run_answer(Connection(), uuid4(), 2, "모르겠습니다", "answer_rejected")
    assert answers == [(2, "모르겠습니다")]
