from datetime import timedelta
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi import APIRouter
from sqlmodel.ext.asyncio.session import AsyncSession

from ..dependencies import get_session
from ..models import domain


router = APIRouter()

@router.get("/users/{user_id}/character", tags=["pvp"])
def get_character(user_id: str, session: AsyncSession = Depends(get_session)) -> domain.CharacterProfile:
    # dummy
    return domain.CharacterProfile(
        user_id=user_id,
        username='dummy',
        level=1, experience=0, power=100.0,
        abilities=domain.AbilityScores(strength=1, defence=1, speed=1, weight=1, combinations=1),
        energy=domain.CharacterEnergy(
            remaining=20,
            maximum=100,
            time_to_restore=timedelta(hours=2, minutes=10)
        )
    )

@router.post("/users/{user_id}/levelup", tags=["pvp"])
def level_up(request: domain.LevelupRequest, session: AsyncSession = Depends(get_session)) -> domain.AbilityScores:
    return HTTPException(status_code=501, detail="not implemented")

@router.post("/users/{user_id}/pvp", tags=["pvp"])
def search_match(user_id: str, session: AsyncSession = Depends(get_session)) -> domain.PVPMatch:
    return HTTPException(status_code=501, detail="not implemented")

@router.post("/pvp/{match_id}/start", tags=["pvp"])
def start_match(match_id: UUID, session: AsyncSession = Depends(get_session)) -> domain.PVPMatchResult:
    return HTTPException(status_code=501, detail="not implemented")