"""실제 공급자 호출 없이 단 한 번의 예산 경유 합성과 실패 처리를 확인한다."""

import asyncio
import importlib.util
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load_smoke(state):
    class TtsError(Exception):
        def __init__(self, reason):
            self.reason = reason

    class Redis:
        @classmethod
        def from_url(cls, url, **kwargs):
            state["redis_url"] = url
            return cls()

        async def hmget(self, key, fields):
            return [1000000, 9, 0, 0, b"epoch"]

        async def info(self, section):
            return {"run_id": state.get("epoch", "epoch")}

        async def aclose(self):
            state["closed"] = True

    class Budget:
        def __init__(self, redis, **kwargs):
            state["budget_configuration"] = kwargs
            self.period = datetime.now(UTC).strftime("%Y-%m")
            self.key = "private-project-budget-key"

    class Client:
        def __init__(self, settings, *, budget):
            state["budget"] = budget

        async def synthesize(self, text, persona):
            state["calls"] = state.get("calls", 0) + 1
            state["text"] = text
            if state.get("error"):
                raise TtsError(state["error"])
            return SimpleNamespace(
                data=state.get("audio", b"ID3" + b"x" * 100), mime_type="audio/mpeg"
            )

    settings = SimpleNamespace(
        redis_url="redis://private",
        require_tts=lambda: SimpleNamespace(
            timeout_seconds=20, budget_project="private-project", monthly_character_limit=1000000
        ),
    )
    modules = {
        name: ModuleType(name)
        for name in (
            "redis",
            "redis.asyncio",
            "app",
            "app.core",
            "app.core.config",
            "app.features",
            "app.features.interview",
            "app.features.interview.tts_budget",
            "app.integrations",
            "app.integrations.tts",
            "app.integrations.tts.google",
        )
    }
    modules["redis.asyncio"].Redis = Redis
    modules["app.core.config"].get_settings = lambda: settings
    modules["app.features.interview.tts_budget"].RedisCharacterBudget = Budget
    modules["app.integrations.tts.google"].GoogleTTSClient = Client
    modules["app.integrations.tts.google"].TtsError = TtsError
    spec = importlib.util.spec_from_file_location(
        "tts_smoke_under_test", ROOT / ".github/scripts/tts_smoke_payload.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


class SmokeTests(unittest.TestCase):
    def run_smoke(self, state, period=None):
        module = load_smoke(state)
        return asyncio.run(
            module.smoke(1000000, period or datetime.now(UTC).strftime("%Y-%m"), "a" * 32)
        )

    def test_one_synthesis_uses_production_budget_and_consumes_nine_characters(self):
        state = {}
        result = self.run_smoke(state)
        self.assertTrue(result["ok"])
        self.assertEqual(state["calls"], 1)
        self.assertEqual(state["text"], "음성 확인입니다.")
        self.assertEqual(len(state["text"]), 9)
        self.assertEqual(
            state["budget_configuration"], {"project": "private-project", "monthly_limit": 1000000}
        )
        self.assertEqual(result["snapshot"]["remaining"], 999991)
        self.assertEqual(result["audioBytes"], 103)
        self.assertTrue(result["mp3Header"])
        self.assertTrue(state["closed"])
        self.assertFalse(result["cloudUsageVerified"])
        self.assertNotIn("private", str(result))

    def test_timeout_never_retries_and_closes_redis(self):
        state = {"error": "timeout"}
        result = self.run_smoke(state)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "timeout")
        self.assertEqual(state["calls"], 1)
        self.assertTrue(state["closed"])

    def test_invalid_audio_or_changed_redis_never_passes(self):
        for state in ({"audio": b"x" * 100}, {"epoch": "changed"}):
            with self.subTest(state=state):
                self.assertFalse(self.run_smoke(state)["ok"])
                self.assertEqual(state["calls"], 1)

    def test_wrong_month_never_synthesizes(self):
        state = {}
        self.assertEqual(self.run_smoke(state, "2000-01")["code"], "period_changed")
        self.assertNotIn("calls", state)


if __name__ == "__main__":
    unittest.main()
