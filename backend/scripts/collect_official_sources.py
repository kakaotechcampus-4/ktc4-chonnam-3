"""공식 자료 catalog를 확인하거나 명시한 개발·시험 DB에 불변 원문을 수집한다."""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.features.knowledge.official_catalog import OfficialSourceError, load_catalog
from app.features.knowledge.official_collection import collect_official_catalog
from app.integrations.search.tavily import SearchBudget, TavilyClient
from scripts.configure_ai_knowledge import KnowledgeTarget, _target_identity


def validate_collection_target(settings: Settings, target: KnowledgeTarget) -> str:
    if settings.app_env not in {"local", "dev"}:
        raise OfficialSourceError("explicit_nonproduction_target_required")
    # asyncpg는 URL query의 host/database를 경로보다 우선하므로 우회 옵션을 허용하지 않는다.
    if make_url(settings.database_url).query:
        raise OfficialSourceError("database_query_options_not_permitted")
    return _target_identity(settings.database_url, target)


async def verify_collection_database(engine: AsyncEngine, target: KnowledgeTarget) -> None:
    async with engine.connect() as connection:
        if await connection.scalar(select(func.current_database())) != target.database:
            raise OfficialSourceError("connected_database_mismatch")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list", action="store_true", help="설정·DB·공급자를 읽지 않고 catalog만 기록"
    )
    parser.add_argument("--key", action="append", default=[], help="수집할 catalog key, 최대16개")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--profile", choices=("development", "test"))
    parser.add_argument("--target-host")
    parser.add_argument("--target-port", type=int)
    parser.add_argument("--target-database")
    parser.add_argument("--actor")
    parser.add_argument("--max-calls", type=int, default=2)
    parser.add_argument("--max-credits", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="생략하면 네트워크·DB 없는 dry-run")
    args = parser.parse_args(argv)
    if args.max_calls <= 0 or args.max_credits <= 0 or args.max_calls > 16 or args.max_credits > 16:
        parser.error("collection budgets must be positive and at most 16")
    if args.list and (args.apply or args.key):
        parser.error("catalog listing cannot collect sources")
    if not args.list and not all(
        (
            args.key,
            args.profile,
            args.target_host,
            args.target_port,
            args.target_database,
            args.actor,
        )
    ):
        parser.error("collection requires keys, actor and explicit target")

    async def operate(settings: Settings) -> dict[str, object]:
        target = KnowledgeTarget(
            args.profile, args.target_host, args.target_port, args.target_database
        )
        target_hash = validate_collection_target(settings, target)
        budget = SearchBudget(args.max_calls, args.max_credits)
        if not args.apply:
            result = await collect_official_catalog(
                None,
                catalog_keys=tuple(args.key),
                provider=None,
                budget=budget,
                actor=args.actor,
                apply=False,
            )
        else:
            engine = create_async_engine(settings.database_url)
            try:
                # 실제 DB 확인을 HTTP·원문 저장보다 먼저 완료한다. dry-run에서는 접속하지 않는다.
                await verify_collection_database(engine, target)
                provider = TavilyClient(settings.require_tavily())
                result = await collect_official_catalog(
                    async_sessionmaker(engine, expire_on_commit=False),
                    catalog_keys=tuple(args.key),
                    provider=provider,
                    budget=budget,
                    actor=args.actor,
                    apply=True,
                )
            finally:
                await engine.dispose()
        return {**result, "target_sha256": target_hash, "profile": target.profile}

    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # 감사 파일은 재실행으로 덮어쓰지 않고 접속정보·키·공급자 오류 원문은 기록하지 않는다.
        with args.output.open("x", encoding="utf-8") as output:
            try:
                result = (
                    {
                        "mode": "catalog_only",
                        "catalog_version": "official-catalog.v1",
                        "sources": [asdict(item) for item in load_catalog()],
                    }
                    if args.list
                    else asyncio.run(operate(Settings(_env_file=args.env_file)))
                )
                output.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            except Exception:
                output.write(
                    json.dumps({"mode": "failed", "error_code": "official_collection_failed"})
                    + "\n"
                )
                raise
    except Exception:
        print(
            "Official collection failed; preserve audit and check explicit target/settings.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
