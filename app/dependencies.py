import os

from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine

dsn = os.environ['BROAPI_DB_DSN'] # "postgresql+asyncpg://postgres:secret@127.0.0.1:5432/brocoin"

engine = create_async_engine(dsn, echo=True, future=True)

async def get_session() -> AsyncSession: # type: ignore ¯\_(ツ)_/¯
    async_session = sessionmaker(
        engine, class_ = AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session