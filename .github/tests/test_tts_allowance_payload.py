"""외부 패키지 없이 실제 예산 함수를 연결해 최초 등록의 변경 경계를 확인한다."""

import asyncio
import importlib.util
import json
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
OPERATION = "a" * 32


class RedisError(Exception):
    pass


class WatchError(RedisError):
    pass


class ResponseError(RedisError):
    pass


class TtsError(Exception):
    pass


class Pipeline:
    def __init__(self, client):
        self.client = client
        self.commands = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def watch(self, key):
        self.client.watched = key

    async def exists(self, _key):
        return bool(self.client.ledger)

    def multi(self):
        self.client.multi_called = True

    def execute_command(self, *arguments):
        self.commands.append(arguments)

    async def execute(self, **_kwargs):
        if self.client.watch_conflict:
            raise WatchError("private-connection-value")
        if self.client.execute_error:
            if isinstance(self.client.execute_error, ResponseError):
                return [self.client.execute_error]
            raise self.client.execute_error
        self.client.committed_commands = self.commands
        self.client.assert_single_command = len(self.commands) == 1
        _, _script, _keys, _key, epoch, cap, requested, metadata, audit = self.commands[0]
        limit = min(cap, requested)
        self.client.ledger = {
            "run_id": epoch.encode(),
            "limit": str(limit).encode(),
            "used": b"0",
            "pending": b"0",
            "uncertain": b"0",
            "initialization_metadata": metadata.encode(),
            "operator_allowance_authorization": audit.encode(),
        }
        return [[limit, 0]]


class Redis:
    active = None

    def __init__(self):
        self.ledger = {}
        self.epochs = []
        self.epoch = "epoch"
        self.watch_conflict = False
        self.execute_error = None
        self.verification_error = False
        self.committed_commands = []
        self.multi_called = False
        self.closed = False

    @classmethod
    def from_url(cls, *_args, **_kwargs):
        return cls.active

    def pipeline(self, **_kwargs):
        return Pipeline(self)

    async def info(self, _section):
        return {"run_id": self.epochs.pop(0) if self.epochs else self.epoch}

    async def hmget(self, _key, fields):
        if self.verification_error:
            raise OSError("private-redis-url")
        return [self.ledger.get(field) for field in fields]

    async def aclose(self):
        self.closed = True


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class AllowancePayloadTests(unittest.TestCase):
    def setUp(self):
        self.redis = Redis.active = Redis()
        self.period = datetime.now(UTC).strftime("%Y-%m")
        self.authorized_at = datetime.now(UTC).isoformat()
        self.tts = SimpleNamespace(
            timeout_seconds=20,
            monthly_character_limit=1000000,
            budget_project="private-project",
        )
        self.settings = SimpleNamespace(
            redis_url="redis://private-url", require_tts=lambda: self.tts
        )
        modules = {
            name: ModuleType(name)
            for name in (
                "redis",
                "redis.asyncio",
                "redis.exceptions",
                "app",
                "app.core",
                "app.core.config",
                "app.features",
                "app.features.interview",
                "app.integrations",
                "app.integrations.tts",
                "app.integrations.tts.google",
            )
        }
        modules["redis.asyncio"].Redis = Redis
        for name, value in (
            ("RedisError", RedisError),
            ("WatchError", WatchError),
            ("ResponseError", ResponseError),
        ):
            setattr(modules["redis.exceptions"], name, value)
        modules["app.core.config"].get_settings = lambda: self.settings
        modules["app.integrations.tts.google"].TtsError = TtsError
        modules["app.integrations.tts.google"].CharacterReservation = SimpleNamespace
        self.module_patch = patch.dict(sys.modules, modules)
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)
        self.budget = load_module(
            "app.features.interview.tts_budget", "backend/app/features/interview/tts_budget.py"
        )
        self.addCleanup(sys.modules.pop, "app.features.interview.tts_budget", None)
        self.payload = load_module(
            "tts_allowance_payload_unit", ".github/scripts/tts_allowance_payload.py"
        )
        self.addCleanup(sys.modules.pop, "tts_allowance_payload_unit", None)
        self.sleeps = []

        async def sleep(seconds):
            self.sleeps.append(seconds)

        self.sleep_patch = patch.object(self.payload.asyncio, "sleep", side_effect=sleep)
        self.sleep_patch.start()
        self.addCleanup(self.sleep_patch.stop)

    def run_payload(self, requested=1000000, **kwargs):
        return asyncio.run(
            self.payload.initialize_allowance(
                requested,
                kwargs.pop("period", self.period),
                self.authorized_at,
                OPERATION,
                **kwargs,
            )
        )

    def test_initialization_uses_existing_lua_and_records_operator_source_atomically(self):
        result = self.run_payload()
        self.assertTrue(result["ok"])
        self.assertTrue(result["applied"])
        self.assertEqual(result["snapshot"], {"limit": 1000000, "used": 0, "remaining": 1000000})
        self.assertEqual(self.sleeps, [25])
        self.assertTrue(self.redis.closed)
        self.assertTrue(self.redis.assert_single_command)
        command = self.redis.committed_commands[0]
        self.assertIn(self.budget._INITIALIZE, command[1])
        self.assertIn("redis.call('TIME')", command[1])
        self.assertLess(
            command[1].index("TTS_PERIOD_CHANGED"), command[1].index("initialize_existing")
        )
        self.assertIn("operator_allowance_authorization", command[1])
        audit = json.loads(self.redis.ledger["operator_allowance_authorization"])
        self.assertFalse(audit["cloudUsageVerified"])
        self.assertEqual(audit["allowanceSource"], "user_requested_amount")
        self.assertEqual(audit["operationId"], OPERATION)
        metadata = json.loads(self.redis.ledger["initialization_metadata"])
        self.assertEqual(metadata["basis"], "operator_confirmed_remaining")

    def test_any_existing_ledger_is_preserved_without_wait_or_write(self):
        for ledger in ({"used": b"174"}, {"pending": b"10", "uncertain": b"5"}):
            with self.subTest(ledger=ledger):
                self.redis.ledger = ledger.copy()
                result = self.run_payload()
                self.assertEqual(result["code"], "ledger_exists")
                self.assertFalse(result["applied"])
                self.assertEqual(self.redis.ledger, ledger)
                self.assertFalse(self.redis.multi_called)
                self.assertEqual(self.sleeps, [])

    def test_watch_conflict_is_not_retried_and_does_not_apply(self):
        self.redis.watch_conflict = True
        result = self.run_payload()
        self.assertEqual(result["code"], "concurrent_change")
        self.assertEqual(result["mutationState"], "not_applied")
        self.assertFalse(self.redis.ledger)
        self.assertEqual(self.sleeps, [25])

    def test_redis_restart_or_period_change_refuses_before_transaction(self):
        self.redis.epochs = ["before", "after"]
        result = self.run_payload()
        self.assertEqual(result["code"], "redis_epoch_changed")
        self.assertFalse(self.redis.multi_called)
        with patch.object(self.payload, "current_period", side_effect=[self.period, "2099-01"]):
            self.redis.epochs = []
            result = self.run_payload()
        self.assertEqual(result["code"], "period_changed")
        self.assertFalse(self.redis.multi_called)

    def test_atomic_month_guard_rejection_does_not_report_applied(self):
        self.redis.execute_error = ResponseError("TTS_PERIOD_CHANGED")
        result = self.run_payload()
        self.assertEqual(result["code"], "period_changed")
        self.assertFalse(result["applied"])
        self.assertFalse(self.redis.ledger)

    def test_connection_loss_during_exec_is_unknown_and_never_exposes_exception(self):
        self.redis.execute_error = OSError("private-key-and-url")
        result = self.run_payload()
        self.assertIsNone(result["applied"])
        self.assertEqual(result["mutationState"], "unknown")
        self.assertNotIn("private", json.dumps(result))

    def test_verification_failure_after_commit_preserves_applied_status(self):
        self.redis.verification_error = True
        result = self.run_payload()
        self.assertFalse(result["ok"])
        self.assertTrue(result["applied"])
        self.assertEqual(result["mutationState"], "applied")
        self.assertTrue(self.redis.ledger)

    def test_invalid_amount_timeout_or_month_never_starts_mutation(self):
        for amount in (True, 0, -1, 1000001):
            self.assertEqual(self.run_payload(amount)["code"], "invalid_allowance")
        self.assertEqual(self.run_payload(period="2099-01")["code"], "period_changed")
        self.tts.timeout_seconds = 26
        self.assertEqual(self.run_payload()["code"], "unsupported_tts_timeout")
        self.tts.timeout_seconds = 20
        self.tts.monthly_character_limit = 999999
        self.assertEqual(self.run_payload()["code"], "allowance_exceeds_configuration")
        self.assertFalse(self.redis.multi_called)


if __name__ == "__main__":
    unittest.main()
