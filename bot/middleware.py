from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bot.db.base import async_session_maker
from bot.db.models import User


class UpsertUserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user:
            async with async_session_maker() as session:
                stmt = pg_insert(User).values(id=user.id, username=user.username)
                stmt = stmt.on_conflict_do_update(
                    index_elements=[User.id],
                    set_={"username": stmt.excluded.username},
                )
                await session.execute(stmt)
                await session.commit()

        return await handler(event, data)
