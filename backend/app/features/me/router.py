"""Authenticated landing reads."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.db.models.user import User
from app.db.session import get_db
from app.features.me import service
from app.features.me.schemas import (
    HomeResponse,
    InterviewListResponse,
    MeProfileResponse,
    MeResponse,
)

router = APIRouter(prefix="/me", tags=["me"])
Database = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(current_user)]


@router.get("", response_model=MeResponse)
async def me(db: Database, user: CurrentUser) -> MeResponse:
    return await service.get_me(db, user)


@router.get("/home", response_model=HomeResponse)
async def home(db: Database, user: CurrentUser) -> HomeResponse:
    return await service.get_home(db, user)


@router.get("/profile", response_model=MeProfileResponse)
async def profile(db: Database, user: CurrentUser) -> MeProfileResponse:
    return await service.get_profile(db, user)


@router.get("/interviews", response_model=InterviewListResponse)
async def interviews(
    db: Database,
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> InterviewListResponse:
    return await service.get_interviews(db, user, page=page, size=size)
