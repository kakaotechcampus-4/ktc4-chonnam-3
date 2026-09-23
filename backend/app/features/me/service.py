"""Read existing account, synchronization and interview data for landing pages."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, Reason
from app.db.models.user import User
from app.features.me import queries
from app.features.me.schemas import (
    AnalysisPanel,
    GithubProfile,
    HomeResponse,
    InterviewListResponse,
    InterviewStats,
    InterviewSummary,
    LanguageRatio,
    MeProfileResponse,
    MeResponse,
    RecentInterview,
)


async def get_me(db: AsyncSession, user: User) -> MeResponse:
    account = await queries.github_account(db, user.id)
    return MeResponse(
        name=user.name,
        avatar_url=user.avatar_url,
        github_linked=account is not None and account.token_status == "valid",
    )


async def get_profile(db: AsyncSession, user: User) -> MeProfileResponse:
    account = await queries.github_account(db, user.id)
    count, average = await queries.interview_stats(db, user.id)
    recent = await queries.completed_interviews(db, user.id, limit=1)
    position = recent[0][1].position if recent and recent[0][1] else None
    linked = account is not None and account.token_status == "valid"
    return MeProfileResponse(
        name=user.name,
        avatar_url=user.avatar_url or "",
        login_id=account.login if account else None,
        joined_at=user.created_at,
        desired_position=position,
        github=GithubProfile(
            linked=linked,
            login=account.login if linked and account else None,
            public_repo_count=account.public_repo_count if linked and account else None,
        ),
        interview_summary=InterviewStats(total_count=count, average_score=average),
    )


def _recent(row: queries.InterviewRow) -> RecentInterview:
    interview, posting, report = row
    return RecentInterview(
        id=interview.id,
        position=(posting.position or "") if posting else "",
        company_name=posting.company_name if posting else None,
        total_score=float(report.total_score) if report else None,
        completed_at=interview.completed_at,
    )


async def get_home(db: AsyncSession, user: User) -> HomeResponse:
    account = await queries.github_account(db, user.id)
    if account is not None and account.token_status != "valid":
        raise AppError(Reason.GITHUB_TOKEN_INVALID)
    count = await queries.public_repository_count(db, user.id)
    job = await queries.latest_sync(db, user.id)
    summary = await queries.profile_summary(db, user.id)
    response = HomeResponse(
        name=user.name,
        github_linked=account is not None,
        repository_count=count,
        analysis_status="no_repository",
        analysis=None,
        recent_interviews=[],
    )
    if job is not None and job.status in ("queued", "running"):
        response.analysis_status = "syncing"
    elif job is not None and job.status in ("failed", "partial", "canceled"):
        raise AppError(
            Reason.INTERNAL_ERROR, message="저장소 동기화에 실패했습니다. 다시 로그인해주세요."
        )
    elif count == 0:
        response.analysis_status = "no_repository"
    elif summary is None:
        # 저장소 목록 수집만 끝난 상태를 AI 프로필 분석 완료로 표시하지 않는다.
        response.analysis_status = "no_interview"
    else:
        response.analysis_status = "completed"
        response.analysis = AnalysisPanel(
            based_on_repo_count=summary.based_on_repo_count,
            languages=[LanguageRatio.model_validate(item) for item in summary.languages],
            project_types=summary.project_types,
            role_summary=summary.role_summary or "",
        )
        response.recent_interviews = [
            _recent(row) for row in await queries.completed_interviews(db, user.id, limit=3)
        ]
    return response


async def get_interviews(
    db: AsyncSession, user: User, *, page: int, size: int
) -> InterviewListResponse:
    count, average = await queries.interview_stats(db, user.id)
    rows = await queries.completed_interviews(db, user.id, limit=size, offset=(page - 1) * size)
    names = await queries.repository_names(db, user.id, [row[0].id for row in rows])
    return InterviewListResponse(
        interviews=[
            InterviewSummary(
                **_recent(row).model_dump(),
                tech_stack=row[1].skill_tags if row[1] else [],
                career_level="",
                repository_names=names.get(row[0].id, []),
                status="completed",
                started_at=row[0].started_at,
            )
            for row in rows
        ],
        total=count,
        page=page,
        size=size,
        average_score=average,
    )
