"""seed_all 이 두 시드를 같은 transaction 안에서 순서대로 부르는지 확인한다 (task-03)."""

from unittest import mock

from scripts import seed_all as seed_all_module


async def test_seed_all_calls_both_seeds_in_one_transaction() -> None:
    session = mock.MagicMock()
    session.begin = mock.MagicMock()
    session.begin.return_value.__aenter__ = mock.AsyncMock()
    session.begin.return_value.__aexit__ = mock.AsyncMock(return_value=False)

    session_factory = mock.MagicMock()
    session_factory.return_value.__aenter__ = mock.AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = mock.AsyncMock(return_value=False)

    calls: list[str] = []

    async def fake_score_criteria(passed_session):
        assert passed_session is session
        calls.append("score_criteria")

    async def fake_domain_frames(passed_session):
        assert passed_session is session
        calls.append("domain_question_frames")

    with (
        mock.patch.object(seed_all_module, "get_session_factory", return_value=session_factory),
        mock.patch.object(seed_all_module, "seed_score_criteria", fake_score_criteria),
        mock.patch.object(seed_all_module, "seed_domain_question_frames", fake_domain_frames),
    ):
        await seed_all_module.seed_all()

    assert calls == ["score_criteria", "domain_question_frames"]
