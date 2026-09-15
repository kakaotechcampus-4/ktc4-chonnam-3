from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.features.me import service
from app.features.me.schemas import MeResponse

router = APIRouter()


@router.get("/me", response_model=MeResponse)
async def me(session: DbSession, user: CurrentUser) -> MeResponse:
    return await service.identity(session, user)
