from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.db.base import async_session_maker
from bot.db.models import FavoriteLeague, FavoriteTeam, League, Team
from bot.keyboards.main_menu import main_menu_kb

router = Router()


async def render_my(user_id: int) -> str:
    async with async_session_maker() as session:
        leagues = (
            await session.execute(
                select(League).join(FavoriteLeague, FavoriteLeague.league_id == League.id)
                .where(FavoriteLeague.user_id == user_id)
                .order_by(League.name)
            )
        ).scalars().all()
        teams = (
            await session.execute(
                select(Team).join(FavoriteTeam, FavoriteTeam.team_id == Team.id)
                .where(FavoriteTeam.user_id == user_id)
                .order_by(Team.name)
            )
        ).scalars().all()

    if not leagues and not teams:
        return "⭐ Подписок пока нет. Открой раздел «Лиги» или «Команды» в меню."

    parts = ["⭐ <b>Твои подписки</b>\n"]
    if leagues:
        parts.append("🏆 <b>Лиги:</b>")
        parts.extend(f"  • {lg.name} ({lg.country})" for lg in leagues)
    if teams:
        parts.append("\n⚽ <b>Команды:</b>")
        parts.extend(f"  • {t.name}" for t in teams)
    return "\n".join(parts)


@router.message(Command("my"))
async def cmd_my(message: Message) -> None:
    text = await render_my(message.from_user.id)
    await message.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "my")
async def cb_my(query: CallbackQuery) -> None:
    text = await render_my(query.from_user.id)
    await query.message.edit_text(text, reply_markup=main_menu_kb(), parse_mode="HTML")
    await query.answer()
