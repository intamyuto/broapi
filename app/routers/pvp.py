from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from typing import Tuple

import math
import random

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from sqlalchemy.orm import load_only
from sqlalchemy.exc import NoResultFound
from sqlalchemy import tablesample, func, or_, and_, case, Integer
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from ..dependencies import get_session, send_notifications
from ..models import domain, db


router = APIRouter()

@router.get("/users/{user_id}/character", tags=["pvp"])
async def get_character(user_id: int, session: AsyncSession = Depends(get_session)) -> domain.CharacterProfile:
    scalar_result = await session.exec(select(db.PVPCharacter).where(db.PVPCharacter.user_id == user_id))
    db_character = scalar_result.one_or_none()
    if not db_character:
        try:
            user_scalar = await session.exec(
                select(db.User).where(db.User.ref_code == str(user_id)).limit(1).options(load_only(db.User.username))
            )
            db_user = user_scalar.one()

            abilities = domain.AbilityScores.default()
            db_character = db.PVPCharacter(
                user_id=user_id,
                username="unnamed_bro" if not db_user.username else db_user.username,
                abilities=abilities.model_dump(mode='json'),
                power=abilities.power(),
                level=0,
                experience=0,
                ts_last_match=datetime.now(timezone.utc),
                energy_last_match=2,
                energy_max=2,
                ts_updated=datetime.now(timezone.utc),
                energy_boost=0,
                ts_defences_today=0
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
            select(db.User).where(db.User.ref_code == str(user_id)).limit(1).options(load_only(db.User.score))
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
                load_only(db.PVPCharacter.user_id, db.PVPCharacter.username, db.PVPCharacter.level, db.PVPCharacter.abilities, db.PVPCharacter.power, db.PVPCharacter.ts_premium_until)
            )
        )
        db_player = player_scalar.one()
        player =  await _convert_to_match_competitioner(db_player, is_premium(db_player), session=session)

        match_scalar = await session.exec(
            select(db.PVPMatch).where(db.PVPMatch.player_id==user_id, db.PVPMatch.ts_finished==None)
        )
        db_match = match_scalar.one_or_none()
        if not db_match:
            opponent = await _search_opponent(player.user_id, db_player.level, is_premium(db_player), session=session)
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
            opponent = await _search_opponent(player.user_id, db_player.level, is_premium(db_player), session=session)
            db_match.opponent_id = opponent.user_id
            db_match.ts_updated = ts_now
            session.add(db_match)

        opponent_scalar = await session.exec(
            select(db.PVPCharacter).where(db.PVPCharacter.user_id == db_match.opponent_id).options(
                    load_only(db.PVPCharacter.user_id, db.PVPCharacter.username, db.PVPCharacter.level, db.PVPCharacter.abilities, db.PVPCharacter.power, db.PVPCharacter.ts_premium_until)
                )
            )
        db_opponent = opponent_scalar.one()
        opponent = await _convert_to_match_competitioner(db_opponent, is_premium(db_player), session=session)
        await session.commit()
        return domain.PVPMatch(match_id=db_match.uuid, player=player, opponent=opponent)
    except NoResultFound:
        raise HTTPException(status_code=404, detail="character not found")

@router.post("/pvp/{match_id}/skip", tags=["pvp"])
async def skip_match(match_id: UUID, session: AsyncSession = Depends(get_session)) -> domain.MatchCompetitioner:
    try: 
        match_scalar = await session.exec(
            select(db.PVPMatch).where(db.PVPMatch.uuid == match_id)
        )
        db_match = match_scalar.one()

        opponent_scalar = await session.exec(
            select(db.PVPCharacter).where(db.PVPCharacter.user_id == db_match.opponent_id).options(
                load_only(db.PVPCharacter.ts_invulnerable_until)
            )
        )
        db_opponent = opponent_scalar.one()
        db_opponent.ts_invulnerable_until = None

        player_scalar = await session.exec(
            select(db.PVPCharacter).where(db.PVPCharacter.user_id == db_match.player_id).options(
                load_only(db.PVPCharacter.level, db.PVPCharacter.ts_premium_until)
            )
        )
        db_player = player_scalar.one()

        user_scalar = await session.exec(
            select(db.User).where(db.User.ref_code == str(db_match.player_id)).limit(1)
                .options(
                    load_only(db.User.score)
                )
        )
        db_user = user_scalar.one()

        if db_user.score < 50:
            raise HTTPException(status_code=400, detail="insufficient coins")
        db_user.score -= 50

        opponent = await _search_opponent(db_match.player_id, db_player.level, is_premium(db_player), session=session)
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
async def start_match(match_id: UUID, background_tasks: BackgroundTasks, session: AsyncSession = Depends(get_session)) -> domain.PVPMatchResult:
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

        if db_player.energy_boost > 0:
            db_player.energy_boost = db_player.energy_boost - 1
        else:
            energy_max = 2
            restore_speed = ENERGY_RESTORE_SPEED
            if is_premium(db_player):
                energy_max = 5    
                restore_speed = ENERGY_RESTORE_SPEED_PREMIUM

            energy = _calc_remaining_energy(db_player.energy_last_match, energy_max, restore_speed, db_player.ts_last_match, ts_now)
            if energy < 1.0:
                raise HTTPException(status_code=400, detail="insufficient energy")

            db_player.energy_last_match = energy - 1.0
            db_player.ts_last_match = ts_now

        opponent_scalar = await session.exec(
            select(db.PVPCharacter).where(db.PVPCharacter.user_id == db_match.opponent_id)
        )
        db_opponent = opponent_scalar.one()

        # battle logic (╯°□°)╯︵ ┻━┻
        match_result, stats = await _calculate_match_result(db_match, db_player, db_opponent, session)
        # ┬─┬ノ( º _ ºノ)

        db_match.result = match_result
        db_match.ts_updated = ts_now
        db_match.ts_finished = ts_now

        db_match.loot = None

        opponent_score, opponent_score_delta, player_score_delta = await _change_score(db_player, db_opponent, db_match.result, session)
        db_match.loot = { 'coins': player_score_delta }

        if db_match.result == db.MatchResult.win:
            await _change_level(db_player, db_opponent)
        else:
            await _change_level(db_opponent, db_player)
        
        db_match.stats = stats 

        message = _match_result_notification_message(db_player, db_opponent, db_match.result, opponent_score_delta, opponent_score)
        background_tasks.add_task(send_notifications, db_match.opponent_id, message)

        #  2 hours invulnerability after defence
        db_opponent.ts_invulnerable_until = ts_now + timedelta(minutes=3)
        db_opponent.ts_defences_today += 1
        # if more the 5 defences per day — invulnerable for the day
        if db_opponent.ts_defences_today >= 100: # 5
            today = ts_now.date()
            db_opponent.ts_invulnerable_until = datetime(today.year, today.month, today.day + 1, tzinfo=timezone.utc)
            db_opponent.ts_defences_today = 0

        session.add(db_opponent)
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
    
def _calc_coins_gain_loss(opponent: db.PVPCharacter, score_base: int) -> Tuple[int, int]:
    amount = math.floor(max(0, score_base) * 0.05)
    if opponent.level == 0:
        return 150, -30
    elif opponent.level == 1:
        return 250, -50
    else:
        return amount, -1 * amount

async def _change_score(player: db.PVPCharacter, opponent: db.PVPCharacter, match_resut: db.MatchResult, session: AsyncSession) -> Tuple[int, int]:
    player_user_scalar = await session.exec(
        select(db.User).where(db.User.ref_code == str(player.user_id)).limit(1).options(load_only(db.User.score))
    )
    db_player_user = player_user_scalar.one()

    opponent_user_scalar = await session.exec(
        select(db.User).where(db.User.ref_code == str(opponent.user_id)).limit(1).options(load_only(db.User.score))
    )
    db_opponent_user = opponent_user_scalar.one()

    player_score_delta = 0
    opponent_score_delta = 0
    if match_resut == db.MatchResult.win:
        player_score_delta, opponent_score_delta = _calc_coins_gain_loss(opponent, db_opponent_user.score)
    elif match_resut == db.MatchResult.lose:
        opponent_score_delta, player_score_delta  = _calc_coins_gain_loss(player, db_player_user.score)

    db_player_user.score = max(0, db_player_user.score + player_score_delta)
    db_opponent_user.score = max(0, db_opponent_user.score + opponent_score_delta)

    return db_opponent_user.score, opponent_score_delta, player_score_delta

def _match_result_notification_message(player: db.PVPCharacter, opponent: db.PVPCharacter, match_result: db.MatchResult, score_delta: int, score: int) -> str:
    ts_now = datetime.now(timezone.utc)

    energy_max = 2
    restore_speed = ENERGY_RESTORE_SPEED
    if is_premium(opponent):
        restore_speed = ENERGY_RESTORE_SPEED_PREMIUM
        energy_max = 5

    remaining_energy = _calc_remaining_energy(opponent.energy_last_match, energy_max, restore_speed, opponent.ts_last_match, ts_now)
    energy = math.floor(remaining_energy) + opponent.energy_boost

    if match_result == db.MatchResult.win:
        return f'''⚔️ @{player.username} with {int(math.floor(player.power))} battle power attacked you! ⚔️  
🏆 Winner: @{player.username}  
📃 Result: You lost {score_delta} $BRO 🪙

Your $BRO balance: {score} $BRO 🪙  
Energy remaining: {energy} ⚡️

Level up your stats to win more battles!

'''
    elif match_result == db.MatchResult.lose:
        return f'''⚔️ @{player.username} with {int(math.floor(player.power))} battle power attacked you! ⚔️  
🏆 Winner: @{opponent.username}  
📃 Result: You won {score_delta} $BRO 🪙, +1 EXP

Your $BRO balance: {score} $BRO 🪙  
Energy remaining: {energy} ⚡️

Level up your stats to win more battles!

'''
    else:
        return ''

async def _change_level(player: db.PVPCharacter, opponent: db.PVPCharacter):
    experience_gain = 0
    if player.level > opponent.level:
        experience_gain = 0
    elif player.level == opponent.level:
        experience_gain = 1
    elif opponent.level > player.level and opponent.power > player.power:
        experience_gain = 3
    elif opponent.level > player.level:
        experience_gain = 2

    current_exp = player.experience + experience_gain
    player.experience = current_exp

    for i in domain.exp_table:
        if current_exp - i >= 0:
            pass
        else:
            current_lvl = domain.exp_table.index(i)
            player.level = current_lvl
            break

async def _search_opponent(player_id: int, player_level: int, is_premium: bool, session: AsyncSession) -> domain.MatchCompetitioner:
    sample = tablesample(db.PVPCharacter, func.bernoulli(100), name='sample', seed=func.random())

    min_level = 0
    if player_level == 1:
        min_level = 1
    elif player_level == 2:
        min_level = 1
    else:
        min_level = player_level - 2

    opponent_id_scalar = await session.exec(
        select(sample.c.user_id).where(
            and_(sample.c.level <= player_level + 2,
                and_(sample.c.level >= min_level,
                    and_(sample.c.user_id != player_id, 
                        or_(sample.c.ts_invulnerable_until == None, 
                            sample.c.ts_invulnerable_until < func.now()
                        )
                    )
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
                load_only(db.PVPCharacter.user_id, db.PVPCharacter.username, db.PVPCharacter.level, db.PVPCharacter.abilities, db.PVPCharacter.power, db.PVPCharacter.ts_invulnerable_until, db.PVPCharacter.ts_premium_until)
            )
        )
    db_opponent = opponent_scalar.one()

    # reserve character for 30min
    ts_now = datetime.now(timezone.utc)
    ts_invulnerable_until = ts_now + timedelta(minutes=30)
    db_opponent.ts_invulnerable_until = ts_invulnerable_until
    db_opponent.ts_updated = ts_now
    session.add(db_opponent)

    return await _convert_to_match_competitioner(db_opponent, is_premium, session=session)

def _convert_from_db_character(db_obj: db.PVPCharacter) -> domain.CharacterProfile:
    ts_now = datetime.now(timezone.utc)

    premium = is_premium(db_obj)

    energy_max = 2
    restore_speed = ENERGY_RESTORE_SPEED
    if premium:
        energy_max = 5
        restore_speed = ENERGY_RESTORE_SPEED_PREMIUM

    remaining_energy = _calc_remaining_energy(db_obj.energy_last_match, energy_max, restore_speed, db_obj.ts_last_match, ts_now)
    time_to_restore = _calc_time_to_restore(remaining_energy, energy_max, restore_speed)
    experience = _calc_exp(db_obj)

    profile = domain.CharacterProfile(
        user_id=db_obj.user_id,
        username=db_obj.username,
        level=db_obj.level, 
        experience=experience,
        power=math.floor(db_obj.power),
        abilities=domain.AbilityScores(**db_obj.abilities),
        energy=domain.CharacterEnergy(
            remaining=math.floor(remaining_energy) + db_obj.energy_boost,
            maximum=energy_max,
            time_to_restore=time_to_restore,
        )
    )

    if premium:
        profile.premium = domain.CharacterProfilePremium(
            active=True,
            until=db_obj.ts_premium_until.date() + timedelta(days=1)
        )

    return profile


def _calc_exp(db_obj: db.PVPCharacter) -> domain.CharacterExperience:
    exp = db_obj.experience
    max_exp = 2
    for i in domain.exp_table:
        if exp - i >= 0:
            pass
        else:
            max_exp = i
            break

    if db_obj.level == 0:
        return domain.CharacterExperience(current_experience=exp, maximum_experience=max_exp)
    
    base = domain.exp_table[db_obj.level - 1]
    return domain.CharacterExperience(current_experience=exp - base, maximum_experience=max_exp - base)

async def _collect_stats(db_obj: db.PVPCharacter, session: AsyncSession):
    scalar = await session.exec(
        select(
                func.count('*').label('total'),
                func.sum(
                    case(
                        (and_(db.PVPMatch.player_id == db_obj.user_id, db.PVPMatch.result == db.MatchResult.win), 1),
                        (and_(db.PVPMatch.opponent_id == db_obj.user_id, db.PVPMatch.result == db.MatchResult.lose), 1),
                        else_=0
                    )
                ).label('won'),
                func.sum(db.PVPMatch.loot['coins'].cast(Integer)).label('loot')
            )
            .select_from(db.PVPMatch)
            .where(
                or_(db.PVPMatch.player_id == db_obj.user_id,
                    db.PVPMatch.opponent_id == db_obj.user_id)
            )
    )
    total, won, loot = scalar.one()

    return domain.PVPStats(total=total, won=won, loot=loot)

async def _convert_to_match_competitioner(db_obj: db.PVPCharacter, player_has_premium: bool, session: AsyncSession) -> domain.MatchCompetitioner:
    competitioner = domain.MatchCompetitioner(
        user_id=db_obj.user_id,
        username=db_obj.username,
        level=db_obj.level,
        power=math.floor(db_obj.power),
        abilities=domain.AbilityScores(**db_obj.abilities),
        premium=is_premium(db_obj)
    )
    
    if player_has_premium:
        competitioner.stats = await _collect_stats(db_obj, session=session)

    return competitioner

ENERGY_RESTORE_SPEED = 4 # per hour
ENERGY_RESTORE_SPEED_PREMIUM = 12 # per hour

def _calc_remaining_energy(energy_base: float, energy_max: int, restore_speed: int, ts_base: datetime, ts_now: datetime) -> float:
    return min(
        energy_base + ((ts_now - ts_base) / timedelta(hours=1)) * restore_speed, 
        energy_max
    )

def _calc_time_to_restore(energy: float, maximum: int, restore_speed: int) -> timedelta:
    if energy >= maximum:
        return timedelta()
    
    return timedelta(hours=(1 - (energy - math.floor(energy))) / restore_speed)


async def _calculate_match_result(match: db.PVPMatch, player: db.PVPCharacter, opponent: db.PVPCharacter,
                            session: AsyncSession) -> tuple[db.MatchResult, dict]:
    """Вычисление результата матча

    :param match: текущий матч
    :param player: нападающий игрок
    :param opponent: обороняющийся игрок
    :param session: сессия бд

    :return result: результат матча
    :return stat: статистика

    """

    count_scalar = await session.exec(
        select(func.count('*')).where(db.PVPMatch.player_id == player.user_id, db.PVPMatch.uuid != match.uuid).select_from(db.PVPMatch)
    )
    if count_scalar.one() == 0:
        return db.MatchResult.win, {'result': db.MatchResult.win, 'comment': 'first match'}

    champion, contestant = opponent, player
    if champion.power < contestant.power:
        champion, contestant = contestant, champion

    champion.power = math.floor(champion.power)
    contestant.power = math.floor(contestant.power)

    gap = (champion.power - contestant.power) / champion.power

    alpha, p = 1.0, .5

    if gap >= 0.75:
        p = 1.0
    elif gap >= 0.51:
        alpha = 1.746
    elif gap >= 0.49:
        alpha = 1.8
    elif gap > 0.44:
        alpha = 1.9
    else:
        alpha = 2.0

    stats = {
        'player_id': player.user_id,
        'opponent_id': opponent.user_id,
        'champion': champion.user_id,
        'champion_power': f'{champion.power}',
        'contestant_power': f'{contestant.power}',
        'gap': f'{gap:.4f}',
        'alpha': f'{alpha:.2f}'
    }

    if p == 1.0:
        result = db.MatchResult.win if champion == player else db.MatchResult.lose
        stats['p'] = '1.0000'
        stats['result'] = result
        return result, stats
    
    p = champion.power * ((1 + gap) ** alpha) / (champion.power + contestant.power)
    dice_roll = random.random()

    stats['p'] = f'{p:.4f}'
    stats['dice_roll'] = f'{dice_roll:.4f}'

    result = db.MatchResult.lose if champion == player else db.MatchResult.win
    if dice_roll <= p:  # champion wins
        result = db.MatchResult.win if champion == player else db.MatchResult.lose

    stats['result'] = result
    return result, stats


def is_premium(player: db.PVPCharacter) -> bool:
    return player.ts_premium_until is not None and datetime.now(timezone.utc).date() < player.ts_premium_until.date() + timedelta(days=1)