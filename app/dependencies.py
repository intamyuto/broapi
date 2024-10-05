import os
import traceback

from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine

from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder

dsn = os.environ['BROAPI_DB_DSN'] # "postgresql+asyncpg://postgres:secret@127.0.0.1:5432/brocoin"

engine = create_async_engine(dsn, echo=True, future=True)

async def get_session() -> AsyncSession: # type: ignore ¯\_(ツ)_/¯
    async_session = sessionmaker(
        engine, class_ = AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session


bot_token = os.environ['BROAPI_BOT_TOKEN']

bot = Bot(token=bot_token)

notifications_whitelist = [240329934, 862139934, 876628085, 860108961, 876241289, 1055487318, 209247857, 1904172074, 5119664278, 6083350394, 7034617135, 624161982, 779238503]

async def send_notifications(user_id: int, message: str):
    if notifications_whitelist and user_id in notifications_whitelist:
        try:
            message = await bot.send_message(chat_id=user_id, text=message, reply_markup=bro_button())
        except Exception:
            traceback.print_exc()
    

def bro_button() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="BROOOO! 👊",
        url=f'https://t.me/itsbrocoinbot/BROSKI',
    )
    return builder.as_markup()
