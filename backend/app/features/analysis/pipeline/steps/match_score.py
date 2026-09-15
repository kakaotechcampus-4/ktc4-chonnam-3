"""step 7 · 매칭 점수 → repo_match_scores.

★ 이 단계는 AI 담당 범위다 (jd_requirements.tech_tags ↔ repo_analyses.tech_stack 대조).
  점수 산식·스케일·정렬·추천 이유는 later.md AI-L07 결정 대기이므로 BE 가 임의로
  확정하지 않는다. ANALYSIS_AI_STEPS_ENABLED=false(기본) 이면 건너뛴다.

★ is_ai_recommended 는 5개 이하로 제한한다 (MAX_AI_RECOMMENDED). is_selected 상한이
  5개라, 추천을 8개 내면 채택률이 구조적으로 62.5% 를 못 넘어 지표가 망가진다.

확정본 §4 repo_match_scores / task-10
"""

import structlog

from app.core.config import get_settings
from app.features.analysis.pipeline.context import RunContext

logger = structlog.get_logger(__name__)


async def run(ctx: RunContext) -> None:
    """AI 매칭 경계. 연결 전에는 no-op."""
    if not get_settings().analysis_ai_steps_enabled:
        logger.info("match_score_skipped", run_id=str(ctx.job.id), reason="ai_not_connected")
        return
    await _delegate_to_ai(ctx)


async def _delegate_to_ai(ctx: RunContext) -> None:
    """AI 패키지(devon_ai) 연결 지점. 결과는 repo_match_scores 에 저장된다."""
    raise NotImplementedError("match_score 는 AI 담당 범위다. 점수 산식(AI-L07) 확정 후 연결한다.")
