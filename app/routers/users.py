from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import Depends, HTTPException
from fastapi import APIRouter
from sqlalchemy.exc import NoResultFound
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from sqlalchemy.orm.attributes import flag_modified

from ..dependencies import get_session
from ..models import domain, db

router = APIRouter()

@router.get("/users/{user_id}", tags=["users"])
async def get_user(user_id: str, session: AsyncSession = Depends(get_session)) -> domain.User:
    try:
        result = await session.exec(select(db.User).where(db.User.ref_code == user_id))
        db_user = result.one()
        await session.commit()

        return _convert_from_db_user(db_user)
    except NoResultFound:
        raise HTTPException(status_code=404, detail="user not found")
    
@router.post("/users", tags=["users"])
async def post_user(user: domain.CreateUser, session: AsyncSession = Depends(get_session)) -> domain.User:
    scalar_result = await session.exec(select(db.User).where(db.User.ref_code == user.user_id))
    db_user = scalar_result.one_or_none()
    if not db_user:
        db_user = db.User()
        db_user.sid = uuid4()
        db_user.username = user.username
        db_user.ref_code = user.user_id
        db_user.refs = {"id": []}
        db_user.score = 25
        db_user.last_score = 0
        db_user.energy = 1000
        db_user.tickets = 25
        db_user.mining_claim = True
        db_user.last_login = datetime.today()
        db_user.reward_streak = 1
        db_user.region = 'eng'
        db_user.advertising_limit = 10
        session.add(db_user)

        ref_score = db.ReferalScore(username=user.user_id, score=0)
        session.add(ref_score)

        if user.ref_code:
            stmt = select(db.User).where(db.User.ref_code == user.ref_code)
            scalar_result = await session.exec(stmt)
            for ref_user in scalar_result:
                ref_user.refs['id'].append(user.user_id)
                flag_modified(ref_user, 'refs')
                if user.premium:
                    ref_user.tickets += 3
                    ref_user.score += 50
                else:
                    ref_user.tickets += 1
                session.add(ref_user)

    await session.commit()
    return _convert_from_db_user(db_user)


@router.post("/stars", tags=["users"])
async def get_stars_link(energy: domain.GetEnergy) -> domain.GetEnergyResponse:
    if int(energy.energy) == 1:
        return 'https://t.me/$2-dS-iy_6EtMCwAAJk_mP8_3zo4'
    if int(energy.energy) == 5:
        return 'https://t.me/$GLpUESy_6EtNCwAA1opihUX-9zg'
    if int(energy.energy) == 20:
        return 'https://t.me/$B6wxwyy_6EtOCwAAhKc_p9CtVJc'



def _convert_from_db_user(user: db.User) -> domain.User:
    # original algorithm as is
    current_time = datetime.now() + timedelta(hours=2)
    time_diff = current_time - user.last_tap
    eight_hours = timedelta(hours=8)
    remaining_time = eight_hours - time_diff
    remaining_hours, remainder = divmod(remaining_time.total_seconds(), 3600)
    remaining_minutes, _ = divmod(remainder, 60)
    formatted_time = f"{int(remaining_hours):02}:{int(remaining_minutes):02}"

    return domain.User(
        score = 0 if user.score is None else user.score,
        tickets = 0 if user.tickets is None else user.tickets,
        boxes = 0 if user.boxes is None else user.boxes,
        ton_balance = 0.0 if user.ton_balanse is None else user.ton_balanse,
        mining = domain.UserMining(
            left=formatted_time, 
            claim=False if user.mining_claim is None else user.mining_claim
        ),
        advertising = domain.UserAdvertising(
            limit = user.advertising_limit, 
            total = 10
        ),
    )
