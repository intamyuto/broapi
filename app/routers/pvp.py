from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import math
import random

from fastapi import Depends, HTTPException
from fastapi import APIRouter

from sqlalchemy.orm import load_only
from sqlalchemy.exc import NoResultFound
from sqlalchemy import tablesample, func
from sqlalchemy.orm import aliased
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
async def level_up(user_id: int, delta: domain.AbilityScoresDelta | None = None, session: AsyncSession = Depends(get_session)) -> domain.LevelupResponse:
    try:
        character_scalar = await session.exec(
            select(db.PVPCharacter).where(db.PVPCharacter.user_id == user_id).options(load_only(db.PVPCharacter.abilities))
        )
        db_character = character_scalar.one()
        abilities = domain.AbilityScores(**db_character.abilities)
        levelup_cost = abilities.upgrade_cost(delta)

        user_scalar = await session.exec(
            select(db.User).where(db.User.ref_code == str(user_id)).options(load_only(db.User.score))
        )
        db_user = user_scalar.one()
        db_user.score = db_user.score - levelup_cost

        if db_user.score < 0:
            raise HTTPException(status_code=400, detail=f"insufficient coins; need another {int(math.fabs(db_user.score))}")
        
        abilities.upgrade(delta)
        db_character.abilities = abilities.model_dump(mode='json')
        db_character.power = abilities.power()
    
        session.add(db_user)
        session.add(db_character)
        await session.commit()
        return domain.LevelupResponse(abilities=abilities, power=db_character.power)
    except NoResultFound:
        raise HTTPException(status_code=404, detail="user or character not found")

@router.post("/users/{user_id}/pvp", tags=["pvp"])
async def search_match(user_id: int, session: AsyncSession = Depends(get_session)) -> domain.PVPMatch:
    try:
        player_scalar = await session.exec(
            select(db.PVPCharacter).where(db.PVPCharacter.user_id==user_id).options(
                load_only(db.PVPCharacter.user_id, db.PVPCharacter.username, db.PVPCharacter.level, db.PVPCharacter.abilities, db.PVPCharacter.power)
            )
        )
        db_player = player_scalar.one()
        player = _convert_to_match_competitioner(db_player)

        match_scalar = await session.exec(
            select(db.PVPMatch).where(db.PVPMatch.player_id==user_id, db.PVPMatch.ts_finished==None)
        )
        db_match = match_scalar.one_or_none()
        if not db_match:
            opponent = await _search_opponent(player.user_id, session=session)
            db_match = db.PVPMatch(
                uuid=uuid4(),
                ts_created=datetime.now(timezone.utc),
                ts_updated=datetime.now(timezone.utc),

                player_id=player.user_id,
                opponent_id=opponent.user_id,
            )
            session.add(db_match)
            await session.commit()
            return domain.PVPMatch(match_id=db_match.uuid, player=player, opponent=opponent)

        opponent_scalar = await session.exec(
            select(db.PVPCharacter).where(db.PVPCharacter.user_id == db_match.opponent_id).options(
                    load_only(db.PVPCharacter.user_id, db.PVPCharacter.username, db.PVPCharacter.level, db.PVPCharacter.abilities, db.PVPCharacter.power)
                )
            )
        db_opponent = opponent_scalar.one()
        opponent = _convert_to_match_competitioner(db_opponent)
        await session.commit()
        return domain.PVPMatch(match_id=db_match.uuid, player=player, opponent=opponent)
    except NoResultFound:
        raise HTTPException(status_code=404, detail="character not found")

@router.post("/pvp/{match_id}/skip", tags=["pvp"])
async def skip_match(match_id: UUID, session: AsyncSession = Depends(get_session)) -> domain.MatchCompetitioner:
    try: 
        match_scalar = await session.exec(
            select(db.PVPMatch).where(db.PVPMatch.uuid==match_id)
        )
        db_match = match_scalar.one()

        opponent = await _search_opponent(db_match.player_id, session=session)
        db_match.opponent_id = opponent.user_id
        
        session.add(db_match)
        await session.commit()
        return opponent

    except NoResultFound:
        raise HTTPException(status_code=404, detail="match not found")

@router.post("/pvp/{match_id}/start", tags=["pvp"])
async def start_match(match_id: UUID, session: AsyncSession = Depends(get_session)) -> domain.PVPMatchResult:
    try: 
        match_scalar = await session.exec(
            select(db.PVPMatch).where(db.PVPMatch.uuid==match_id)
        )
        db_match = match_scalar.one()

        if db_match.ts_finished is not None:
            raise HTTPException(status_code=404, detail="match finished")

        coins = 500

        db_match.result = db.MatchResult.win
        db_match.ts_finished = datetime.now(timezone.utc)
        db_match.loot = { 'coins': coins }
        
        session.add(db_match)
        await session.commit()

        return domain.PVPMatchResult(
            result=domain.MatchResult.win, 
            loot=domain.MatchLoot(coins=coins),
        )
    
    except NoResultFound:
        raise HTTPException(status_code=404, detail="match not found")

async def _search_opponent(player_id: int, session: AsyncSession) -> domain.MatchCompetitioner:
    # todo: character not staged to battle
    # todo: less then 5 matches for 24h
    # todo: last battle more then 2 hours ago

    sample = tablesample(db.PVPCharacter, func.bernoulli(100), name='sample', seed=func.random())
    opponent_id_scalar = await session.exec(
        select(sample.c.user_id).where(sample.c.user_id != player_id)
    )
    opponent_id = random.choice(opponent_id_scalar.all())

    opponent_scalar = await session.exec(
        select(db.PVPCharacter).where(db.PVPCharacter.user_id == opponent_id).options(
                load_only(db.PVPCharacter.user_id, db.PVPCharacter.username, db.PVPCharacter.level, db.PVPCharacter.abilities, db.PVPCharacter.power)
            )
        )
    db_opponent = opponent_scalar.one()
    return _convert_to_match_competitioner(db_opponent)

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

def _convert_to_match_competitioner(db_obj: db.PVPCharacter) -> domain.MatchCompetitioner:
    return domain.MatchCompetitioner(
        user_id=db_obj.user_id,
        username=db_obj.username,
        level=db_obj.level,
        power=db_obj.power,
        abilities=domain.AbilityScores(**db_obj.abilities),
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