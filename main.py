from fastapi import Depends, HTTPException, FastAPI
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import sessionmaker
from sqlmodel import select
from datetime import datetime

import model
import db

app = FastAPI()

engine = create_async_engine("postgresql+asyncpg://postgres:secret@127.0.0.1:5432/brocoin", echo=True, future=True)

async def get_session() -> AsyncSession:
    async_session = sessionmaker(
        engine, class_ = AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session

@app.get("/api/v1/users/{username}")
async def get_user(username: str, session: AsyncSession = Depends(get_session)) -> model.User:
    try:
        result = await session.exec(select(db.User).where(db.User.username == username))
        await session.commit()
        user = result.one()
        return model.User(score = 0 if user.score is None else user.score,
            tickets = 0 if user.tickets is None else user.tickets,
            boxes = 0 if user.boxes is None else user.boxes,
            ton_balance = 0.0 if user.ton_balanse is None else user.ton_balanse,
            mining = model.UserMining(left=datetime.now(), claim=False),
            advertising = model.UserAdvertising(limit = 0, total = 0),
        )
    except NoResultFound:
        raise HTTPException(status_code=404, detail="user not found")
    