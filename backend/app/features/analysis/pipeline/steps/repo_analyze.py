"""step 6 · L1 기본 분석 → repo_analyses(analysis_level='shallow').

★ 이 단계는 AI 담당 범위다. BE 는 호출 경계와 결과 저장만 가진다.
  ANALYSIS_AI_STEPS_ENABLED=false(기본) 이면 호출하지 않고 건너뛴다. 이때 카드에는
  matchScore/recommendReason 이 null 이고 recommended 는 false 로 내려간다.
  true 로 바꾸면 app/llm_tasks/repo_shallow.py 경계를 호출한다 (AI 구현 전에는 실패).

캐시 키는 (repository_id, analysis_level, head_sha, prompt_version) 이다 — push 로
head_sha 가 바뀌면 자동 재분석된다. 일부 레포 실패는 job 실패가 아니라 개별 row 실패다.

확정본 §2 repo_analyses / task-10
"""

import structlog

from app.core.config import get_settings
from app.features.analysis.pipeline.context import RunContext

logger = structlog.get_logger(__name__)


async def run(ctx: RunContext) -> None:
    """AI L1 분석 경계. 연결 전에는 no-op."""
    if not get_settings().analysis_ai_steps_enabled:
        logger.info("repo_analyze_skipped", run_id=str(ctx.job.id), reason="ai_not_connected")
        return
    await _delegate_to_ai(ctx)


async def _delegate_to_ai(ctx: RunContext) -> None:
    """AI 패키지(devon_ai) 연결 지점. 결과는 repo_analyses 에 저장된다."""
    raise NotImplementedError(
        "repo_analyze(L1) 는 AI 담당 범위다. app/llm_tasks/repo_shallow.py 연결 후 구현한다."
    )
