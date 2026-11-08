import asyncio

import pytest
from pydantic import SecretStr

from app.features.interview.tts_budget import RedisCharacterBudget, initialize_budget
from app.integrations.tts.google import BudgetedSpeechSynthesizer, TtsError, TTSSettings


async def test_budget_missing_never_initializes_itself(redis):
    budget = RedisCharacterBudget(redis, project="cloud-project", monthly_limit=100)
    with pytest.raises(TtsError, match="budget_uninitialized"):
        await budget.reserve("질문")
    assert not await redis.exists(budget.key)


async def test_reservation_counts_spaces_and_survives_client_recreation(redis):
    await initialize_budget(
        redis, project="cloud-project", remaining_characters=10, monthly_limit=100
    )
    first = RedisCharacterBudget(redis, project="cloud-project", monthly_limit=100)
    reservation = await first.reserve("가 나\n")
    assert reservation.characters == 4
    await first.settle(reservation, "success")
    second = RedisCharacterBudget(redis, project="cloud-project", monthly_limit=100)
    await second.reserve("123456")
    with pytest.raises(TtsError, match="budget_exhausted"):
        await second.reserve("x")
    assert await redis.hget(second.key, "used") == b"10"
    assert await redis.ttl(second.key) == -1


async def test_concurrent_reservations_cannot_exceed_allowance(redis):
    await initialize_budget(
        redis, project="cloud-project", remaining_characters=10, monthly_limit=100
    )
    budget = RedisCharacterBudget(redis, project="cloud-project", monthly_limit=100)
    values = await asyncio.gather(
        budget.reserve("123456"), budget.reserve("123456"), return_exceptions=True
    )
    assert sum(isinstance(x, TtsError) for x in values) == 1
    assert await redis.hget(budget.key, "used") == b"6"


async def test_unknown_provider_failure_does_not_refund_reserved_characters(redis):
    await initialize_budget(
        redis, project="cloud-project", remaining_characters=5, monthly_limit=100
    )
    budget = RedisCharacterBudget(redis, project="cloud-project", monthly_limit=100)
    receipt = await budget.reserve("12345")
    await budget.settle(receipt, "uncertain")
    assert await redis.hget(budget.key, "used") == b"5"
    with pytest.raises(TtsError, match="budget_exhausted"):
        await budget.reserve("x")


async def test_restored_counter_from_another_redis_process_fails_closed(redis):
    await initialize_budget(
        redis, project="cloud-project", remaining_characters=10, monthly_limit=100
    )
    budget = RedisCharacterBudget(redis, project="cloud-project", monthly_limit=100)
    await redis.hset(budget.key, "run_id", "previous-redis-process")
    with pytest.raises(TtsError, match="budget_epoch_changed"):
        await budget.reserve("x")
    assert await redis.hget(budget.key, "used") == b"0"


async def test_missing_month_does_not_reset_previous_allowance(redis):
    await initialize_budget(
        redis, project="cloud-project", remaining_characters=10, monthly_limit=100, period="2026-11"
    )
    new_month = RedisCharacterBudget(
        redis, project="cloud-project", monthly_limit=100, period="2026-12"
    )
    with pytest.raises(TtsError, match="budget_uninitialized"):
        await new_month.reserve("x")


async def test_explicit_reconciliation_preserves_known_usage_and_uses_confirmed_remaining(redis):
    await initialize_budget(
        redis, project="cloud-project", remaining_characters=10, monthly_limit=100
    )
    budget = RedisCharacterBudget(redis, project="cloud-project", monthly_limit=100)
    receipt = await budget.reserve("1234")
    await budget.settle(receipt, "success")
    snapshot = await initialize_budget(
        redis, project="cloud-project", remaining_characters=2, monthly_limit=100
    )
    assert (snapshot.limit, snapshot.used, snapshot.remaining) == (6, 4, 2)
    await budget.reserve("ab")
    with pytest.raises(TtsError, match="budget_exhausted"):
        await budget.reserve("c")


async def test_reconciliation_subtracts_pending_or_uncertain_provider_calls(redis):
    await initialize_budget(
        redis, project="cloud-project", remaining_characters=10, monthly_limit=100
    )
    budget = RedisCharacterBudget(redis, project="cloud-project", monthly_limit=100)
    receipt = await budget.reserve("1234")
    await budget.settle(receipt, "uncertain")
    snapshot = await initialize_budget(
        redis, project="cloud-project", remaining_characters=2, monthly_limit=100
    )
    assert snapshot.remaining == 0


async def test_cancelled_provider_request_keeps_reservation_as_uncertain(redis):
    await initialize_budget(
        redis, project="cloud-project", remaining_characters=100, monthly_limit=100
    )
    budget = RedisCharacterBudget(redis, project="cloud-project", monthly_limit=100)
    started = asyncio.Event()

    class Waiting:
        async def synthesize(self, text, persona):
            started.set()
            await asyncio.sleep(100)

    settings = TTSSettings(
        voice_map={
            key: "ko-KR-Chirp3-HD-Charon" for key in ("tech_lead", "domain_lead", "hr_manager")
        },
        api_key=SecretStr("test"),
        monthly_character_limit=100,
        budget_project="cloud-project",
    )
    synthesizer = BudgetedSpeechSynthesizer(Waiting(), settings, budget)
    task = asyncio.create_task(synthesizer.synthesize("가 나\n", "tech_lead"))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await redis.hget(budget.key, "used") == b"4"
    assert await redis.hget(budget.key, "uncertain") == b"4"
    assert await redis.hget(budget.key, "pending") == b"0"
