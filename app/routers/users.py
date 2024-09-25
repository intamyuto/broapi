from fastapi import Depends, HTTPException
from fastapi import APIRouter
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodel import select
from datetime import datetime
from sqlalchemy.exc import NoResultFound

from ..dependencies import get_session
from ..models import domain, db

router = APIRouter()

@router.get("/users/{username}", tags=["users"])
async def get_user(username: str, session: AsyncSession = Depends(get_session)) -> domain.User:
    try:
        result = await session.exec(select(db.User).where(db.User.username == username))
        await session.commit()
        user = result.one()
        return domain.User(score = 0 if user.score is None else user.score,
            tickets = 0 if user.tickets is None else user.tickets,
            boxes = 0 if user.boxes is None else user.boxes,
            ton_balance = 0.0 if user.ton_balanse is None else user.ton_balanse,
            mining = domain.UserMining(left=datetime.now(), claim=False),
            advertising = domain.UserAdvertising(limit = 0, total = 0),
        )
    except NoResultFound:
        raise HTTPException(status_code=404, detail="user not found")
    