"""명시한 개발·시험 DB에만 미검수 rubric/frame 초안을 준비한다."""

import argparse
import asyncio
import hashlib
import json
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.models.knowledge import QUESTION_FRAME_AXES, DomainQuestionFrame, ScoreCriterion
from app.db.models.posting import DOMAIN_CATEGORIES
from app.db.models.report import SCORE_KEYS
from scripts.seed_domain_question_frames import DOMAIN_QUESTION_FRAMES
from scripts.seed_score_criteria import SCORE_CRITERIA


class KnowledgeConfigurationError(ValueError):
    """접속 정보나 기존 기준의 원문을 노출하지 않는 설정 오류."""


@dataclass(frozen=True)
class KnowledgeTarget:
    profile: str
    host: str
    port: int
    database: str


def _target_identity(database_url: str, target: KnowledgeTarget) -> str:
    try:
        url = make_url(database_url)
        if (
            url.drivername != "postgresql+asyncpg"
            or not target.host.strip()
            or type(target.port) is not int
            or not 1 <= target.port <= 65535
            or (url.host or "").casefold() != target.host.casefold()
            or (url.port or 5432) != target.port
            or not target.database
            or url.database != target.database
            or target.database in {"postgres", "template0", "template1"}
            or target.profile not in {"development", "test"}
            or target.profile == "test"
            and not target.database.endswith("_test")
        ):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise KnowledgeConfigurationError("Knowledge target not permitted") from None
    # URL·사용자명·비밀번호 대신 명시한 대상의 지문만 감사 결과에 남긴다.
    raw = json.dumps([target.profile, target.host.casefold(), target.port, target.database])
    return hashlib.sha256(raw.encode()).hexdigest()


def validate_target(
    settings: Settings, target: KnowledgeTarget, *, allow_unreviewed: bool
) -> dict[str, Any]:
    if settings.app_env not in {"local", "dev"} or allow_unreviewed is not True:
        raise KnowledgeConfigurationError("Explicit non-production draft permission required")
    return {
        "profile": target.profile,
        "environment": settings.app_env,
        "approval_status": "unreviewed",
        "target_sha256": _target_identity(settings.database_url, target),
    }


def _configure_rows[K, Row: ScoreCriterion | DomainQuestionFrame](
    db: AsyncSession,
    model: type[Row],
    expected: Mapping[K, dict[str, Any]],
    existing: Mapping[K, Row],
    *,
    apply: bool,
) -> int:
    if any(row.is_active and key not in expected for key, row in existing.items()):
        raise KnowledgeConfigurationError("Active knowledge outside the draft bundle")
    changes = 0
    for key, values in expected.items():
        row = existing.get(key)
        # inactive 초안도 다른 사람이 수정했을 수 있으므로 묵시적으로 덮어쓰지 않는다.
        if row is not None and any(getattr(row, field) != value for field, value in values.items()):
            raise KnowledgeConfigurationError("Existing knowledge differs; preserve and review it")
        if row is None or not row.is_active:
            changes += 1
            if apply:
                if row is None:
                    db.add(model(**values, is_active=True))
                else:
                    row.is_active = True
    return changes


async def configure_knowledge(
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    target: KnowledgeTarget,
    *,
    allow_unreviewed: bool,
    actor: str,
    apply: bool = False,
) -> dict[str, Any]:
    audit = validate_target(settings, target, allow_unreviewed=allow_unreviewed)
    if not isinstance(actor, str) or not actor.strip() or len(actor) > 128:
        raise KnowledgeConfigurationError("Explicit actor required")
    engine = sessions.kw.get("bind")
    if engine is None or _target_identity(str(engine.url), target) != audit["target_sha256"]:
        raise KnowledgeConfigurationError("Session target does not match configuration")
    criteria = {item.score_key: asdict(item) for item in SCORE_CRITERIA}
    frames = {
        (item.domain_category, item.axis, 1): {**asdict(item), "display_order": 1}
        for item in DOMAIN_QUESTION_FRAMES
    }
    if (
        len(criteria) != len(SCORE_CRITERIA)
        or set(criteria) != set(SCORE_KEYS)
        or any(
            set(item["rubric"]) != {str(level) for level in range(5)} for item in criteria.values()
        )
        or len(frames) != len(DOMAIN_QUESTION_FRAMES)
        or set(frames)
        != {(category, axis, 1) for category in DOMAIN_CATEGORIES for axis in QUESTION_FRAME_AXES}
    ):
        raise KnowledgeConfigurationError("Incomplete or duplicate draft bundle")
    bundle = dict(criteria=list(criteria.values()), frames=list(frames.values()))
    digest = hashlib.sha256(
        json.dumps(bundle, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    changes = 0
    async with sessions.begin() as db:
        if await db.scalar(select(func.current_database())) != target.database:
            raise KnowledgeConfigurationError("Connected database does not match target")
        # 비어 있는 DB의 동시 초기화도 직렬화한다. 기존 행은 아래에서 잠근 뒤 대조한다.
        await db.execute(text("SELECT pg_advisory_xact_lock(316503206)"))
        existing_criteria = {
            row.score_key: row for row in await db.scalars(select(ScoreCriterion).with_for_update())
        }
        existing_frames = {
            (row.domain_category, row.axis, row.display_order): row
            for row in await db.scalars(select(DomainQuestionFrame).with_for_update())
        }
        changes += _configure_rows(db, ScoreCriterion, criteria, existing_criteria, apply=apply)
        changes += _configure_rows(db, DomainQuestionFrame, frames, existing_frames, apply=apply)
        if apply:
            await db.flush()
    return {
        "format_version": 1,
        **audit,
        "mode": "applied" if apply else "dry_run",
        "actor": actor.strip(),
        "recorded_at": datetime.now(UTC).isoformat(),
        "bundle_sha256": digest,
        "score_keys": sorted(criteria),
        "frame_count": len(frames),
        "changes": changes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--profile", choices=("development", "test"), required=True)
    parser.add_argument("--target-host", required=True)
    parser.add_argument("--target-port", type=int, required=True)
    parser.add_argument("--target-database", required=True)
    parser.add_argument("--allow-unreviewed-drafts", action="store_true")
    parser.add_argument("--actor", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    async def operate(settings: Settings, target: KnowledgeTarget) -> dict[str, Any]:
        engine = create_async_engine(settings.database_url)
        try:
            return await configure_knowledge(
                async_sessionmaker(engine, expire_on_commit=False),
                settings,
                target,
                allow_unreviewed=args.allow_unreviewed_drafts,
                actor=args.actor,
                apply=args.apply,
            )
        finally:
            await engine.dispose()

    try:
        settings = Settings(_env_file=args.env_file)
        target = KnowledgeTarget(
            args.profile, args.target_host, args.target_port, args.target_database
        )
        validate_target(settings, target, allow_unreviewed=args.allow_unreviewed_drafts)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # 이전 감사 기록을 덮지 않고, 기록 경로가 열리는 것을 DB 접근 전에 확인한다.
        with args.output.open("x", encoding="utf-8") as output:
            result = asyncio.run(operate(settings, target))
            output.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    except Exception:
        print(
            "Knowledge configuration failed; preserve audit and check target/settings.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps({"mode": result["mode"], "approval_status": result["approval_status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
