from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi import APIRouter
from sqlmodel.ext.asyncio.session import AsyncSession

from ..dependencies import get_session
from ..models import domain


router = APIRouter()

@router.get("/users/{user_id}/character", tags=["pvp"])
def get_character(user_id: str, session: AsyncSession = Depends(get_session)) -> domain.CharacterProfile:
    return HTTPException(status_code=501, detail="not implemented")

@router.post("/users/{user_id}/levelup", tags=["pvp"])
def level_up(request: domain.LevelupRequest, session: AsyncSession = Depends(get_session)) -> domain.AbilityScores:
    return HTTPException(status_code=501, detail="not implemented")

@router.post("/users/{user_id}/pvp", tags=["pvp"])
def search_match(user_id: str, session: AsyncSession = Depends(get_session)) -> domain.PVPMatch:
    return HTTPException(status_code=501, detail="not implemented")

@router.post("/pvp/{match_id}/start", tags=["pvp"])
def start_match(match_id: UUID, session: AsyncSession = Depends(get_session)) -> domain.PVPMatchResult:
    return HTTPException(status_code=501, detail="not implemented")