from datetime import datetime, timedelta, timezone
from uuid import UUID

import math

from fastapi import Depends, HTTPException
from fastapi import APIRouter

from sqlalchemy.orm import load_only
from sqlalchemy.exc import NoResultFound
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from ..dependencies import get_session
from ..models import domain, db


router = APIRouter()

@router.get("/users/{user_id}/character", tags=["pvp"])
async def get_character(user_id: int, session: AsyncSession = Depends(get_session)) -> domain.CharacterProfile:
    scalar_result = await session.exec(select(db.PVPCharacter).where(db.PVPCharacter.user_id == user_id))
    db_character = scalar_result.one_or_none()
    if not db_character:
        try:
            user_scalar = await session.exec(
                select(db.User).where(db.User.ref_code == str(user_id)).options(load_only(db.User.username))
            )
            db_user = user_scalar.one()

            abilities = domain.AbilityScores.default()
            db_character = db.PVPCharacter(
                user_id=user_id,
                username=db_user.username,
                abilities=abilities.model_dump(mode='json'),
                power=abilities.power(),
                level=1, experience=0,
                ts_last_match=datetime.now(timezone.utc),
                energy_last_match=2,
                energy_max=2,
            )
            session.add(db_character)
        except NoResultFound:
            raise HTTPException(status_code=404, detail="user not found")

    await session.commit()
    return _convert_from_db_character(db_character)

@router.post("/users/{user_id}/levelup", tags=["pvp"])
def level_up(request: domain.LevelupRequest, session: AsyncSession = Depends(get_session)) -> domain.AbilityScores:
    return HTTPException(status_code=501, detail="not implemented")

@router.post("/users/{user_id}/pvp", tags=["pvp"])
def search_match(user_id: str, session: AsyncSession = Depends(get_session)) -> domain.PVPMatch:
    return HTTPException(status_code=501, detail="not implemented")

@router.post("/pvp/{match_id}/start", tags=["pvp"])
def start_match(match_id: UUID, session: AsyncSession = Depends(get_session)) -> domain.PVPMatchResult:
    return HTTPException(status_code=501, detail="not implemented")

def _convert_from_db_character(db_obj: db.PVPCharacter) -> domain.CharacterProfile:
    ts_now = datetime.now(timezone.utc)
    remaining_energy = _calc_remaining_energy(db_obj.energy_last_match, db_obj.energy_max, db_obj.ts_last_match, ts_now)
    time_to_restore = _calc_time_to_restore(remaining_energy, db_obj.energy_max)
    return domain.CharacterProfile(
        user_id=db_obj.user_id,
        username=db_obj.username,
        level=db_obj.level, 
        experience=db_obj.experience,
        power=db_obj.power,
        abilities=domain.AbilityScores(**db_obj.abilities),
        energy=domain.CharacterEnergy(
            remaining=remaining_energy,
            maximum=db_obj.energy_max,
            time_to_restore=time_to_restore,
        )
    )

ENERGY_RESTORE_SPEED = 1 # per hour

def _calc_remaining_energy(energy_base, energy_max: int, ts_base, ts_now: datetime) -> int:
    print(ts_now)
    print(ts_base)
    return min(energy_base + \
        math.floor(
            (ts_now - ts_base) / timedelta(hours=1) * ENERGY_RESTORE_SPEED
        ), energy_max)

def _calc_time_to_restore(energy, maximum: int) -> timedelta:
    if energy == maximum:
        return timedelta()
    return timedelta(hours=(float(maximum) - float(energy)) / ENERGY_RESTORE_SPEED)