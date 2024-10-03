from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import math
import random

from fastapi import Depends, HTTPException
from fastapi import APIRouter

from sqlalchemy.orm import load_only
from sqlalchemy.exc import NoResultFound
from sqlalchemy import tablesample, func, or_, and_
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
        return domain.LevelupResponse(abilities=abilities, power=math.floor(db_character.power))
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
        
        ts_now = datetime.now(timezone.utc)
        if db_match.ts_updated + timedelta(minutes=30) < ts_now:
            opponent = await _search_opponent(player.user_id, session=session)
            db_match.opponent_id = opponent.user_id
            db_match.ts_updated = ts_now
            session.add(db_match)

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

        opponent_scalar = await session.exec(
            select(db.PVPCharacter).where(db.PVPCharacter.user_id == db_match.opponent_id).options(
                load_only(db.PVPCharacter.ts_invulnerable_until)
            )
        )
        db_opponent = opponent_scalar.one()
        db_opponent.ts_invulnerable_until = None

        user_scalar = await session.exec(
            select(db.User).where(db.User.ref_code == str(db_match.player_id))
                .options(
                    load_only(db.User.tickets)
                )
        )
        db_user = user_scalar.one()

        if db_user.tickets < 3:
            raise HTTPException(status_code=404, detail="insufficient tickets")
        db_user.tickets -= 3

        opponent = await _search_opponent(db_match.player_id, session=session)
        db_match.ts_updated = datetime.now(timezone.utc)
        db_match.opponent_id = opponent.user_id
        
        session.add(db_opponent)
        session.add(db_user)
        session.add(db_match)
        await session.commit()
        return opponent

    except NoResultFound:
        raise HTTPException(status_code=404, detail="match not found")

@router.post("/pvp/{match_id}/start", tags=["pvp"])
async def start_match(match_id: UUID, session: AsyncSession = Depends(get_session)) -> domain.PVPMatchResult:
    try: 
        match_scalar = await session.exec(
            select(db.PVPMatch).where(db.PVPMatch.uuid==match_id).options(
                load_only(db.PVPMatch.player_id, db.PVPMatch.opponent_id, db.PVPMatch.ts_updated, db.PVPMatch.ts_finished)
            )
        )
        db_match = match_scalar.one()

        if db_match.ts_finished is not None:
            raise HTTPException(status_code=404, detail="match already finished")
        
        ts_now = datetime.now(timezone.utc)
        if db_match.ts_updated + timedelta(minutes=30) < ts_now:
            raise HTTPException(status_code=400, detail="match expired; find new opponent")

        player_scalar = await session.exec(
            select(db.PVPCharacter).where(db.PVPCharacter.user_id == db_match.player_id)
        )
        db_player = player_scalar.one()

        # energy calculation is incorrect >_<
        if db_player.energy_boost > 0:
            db_player.energy_boost = db_player.energy_boost - 1
        else:
            energy = _calc_remaining_energy(db_player.energy_last_match, db_player.energy_max, db_player.ts_last_match, ts_now)
            if energy < 1:
                raise HTTPException(status_code=400, detail="insufficient energy")
            
            db_player.energy_last_match = energy - 1
            db_player.ts_last_match = ts_now

        opponent_scalar = await session.exec(
            select(db.PVPCharacter).where(db.PVPCharacter.user_id == db_match.opponent_id).options(
                load_only(db.PVPCharacter.power, db.PVPCharacter.ts_defences_today, db.PVPCharacter.ts_updated)
            )
        )
        db_opponent = opponent_scalar.one()

        coins = 500

        # battle logic (╯°□°)╯︵ ┻━┻
        match_result, stats = _calculate_match_result(db_player, db_opponent)
        # ┬─┬ノ( º _ ºノ)

        db_match.result = match_result
        db_match.ts_updated = ts_now
        db_match.ts_finished = ts_now

        db_match.loot = None
        if db_match.result == db.MatchResult.win:
            db_match.loot = { 'coins': coins }   
        db_match.stats = stats 

        user_scalar = await session.exec(
            select(db.User).where(db.User.ref_code == str(db_match.player_id)).options(load_only(db.User.score))
        )
        db_user = user_scalar.one()

        db_user.score += coins

        #  2 hours invulnerability after defence
        db_opponent.ts_invulnerable_until = ts_now + timedelta(hours=2)
        db_opponent.ts_defences_today += 1
        # if more the 5 defences per day — invulnerable for the day
        if db_opponent.ts_defences_today >= 5:
            today = ts_now.date()
            db_opponent.ts_invulnerable_until = datetime(today.year, today.month, today.day + 1, tzinfo=timezone.utc)
            db_opponent.ts_defences_today = 0

        session.add(db_opponent)
        session.add(db_user)
        session.add(db_player)
        session.add(db_match)
        await session.commit()

        result = domain.PVPMatchResult(
            result=domain.MatchResult.win if db_match.result == db.MatchResult.win else domain.MatchResult.lose, 
        )
        if db_match.loot:
            result.loot = domain.MatchLoot(**db_match.loot)

        return result
    
    except NoResultFound:
        raise HTTPException(status_code=404, detail="match not found")

async def _search_opponent(player_id: int, session: AsyncSession) -> domain.MatchCompetitioner:
    sample = tablesample(db.PVPCharacter, func.bernoulli(100), name='sample', seed=func.random())
    opponent_id_scalar = await session.exec(
        select(sample.c.user_id).where(
            and_(sample.c.user_id != player_id, 
                or_(sample.c.ts_invulnerable_until == None, 
                    sample.c.ts_invulnerable_until < func.now()
                )
            )
        )
    )
    opponent_ids = opponent_id_scalar.all()
    if not opponent_ids:
        raise HTTPException(status_code=400, detail="no available opponents; please wait")
    opponent_id = random.choice(opponent_ids)

    opponent_scalar = await session.exec(
        select(db.PVPCharacter)
            .where(db.PVPCharacter.user_id == opponent_id)
            .options(
                load_only(db.PVPCharacter.user_id, db.PVPCharacter.username, db.PVPCharacter.level, db.PVPCharacter.abilities, db.PVPCharacter.power, db.PVPCharacter.ts_invulnerable_until)
            )
        )
    db_opponent = opponent_scalar.one()

    # reserve character for 30min
    ts_now = datetime.now(timezone.utc)
    ts_invulnerable_until = ts_now + timedelta(minutes=30)
    db_opponent.ts_invulnerable_until = ts_invulnerable_until
    db_opponent.ts_updated = ts_now
    session.add(db_opponent)

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
        power=math.floor(db_obj.power),
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
        power=math.floor(db_obj.power),
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

def _calculate_match_result(player: db.PVPCharacter, opponent: db.PVPCharacter) -> tuple[db.MatchResult, dict]:
    champion, contestant = opponent, player
    if champion.power < contestant.power:
        champion, contestant = contestant, champion

    gap = (champion.power - contestant.power) / champion.power

    alpha, p = 1.0, .5
    if gap > 0.5:
        p = 1.0
    elif gap > 0.3:
        alpha = 3.5
    elif gap > 0.2:
        alpha = 2.5
    elif gap > 0.1:
        alpha = 2.0
    
    stats = {
        'player_id': player.user_id,
        'opponent_id': opponent.user_id,
        'champion': champion.user_id,
        'gap': f'{gap:.4f}'
    }

    if p == 1.0:
        result = db.MatchResult.win if champion == player else db.MatchResult.lose
        stats['p'] = '1.0000'
        stats['result'] = result
        return result, stats
    
    p = champion.power * (1 + gap ** alpha) / (champion.power + contestant.power)
    dice_roll = random.random()

    stats['p'] = f'{p:.4f}'
    stats['dice_roll'] = f'{dice_roll:.4f}'

    result = db.MatchResult.lose if champion == player else db.MatchResult.win
    if dice_roll <= p: # champion wins
        result = db.MatchResult.win if champion == player else db.MatchResult.lose

    stats['result'] = result
    return result, stats