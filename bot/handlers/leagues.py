from aiogram import Router
from aiogram.types import CallbackQuery
from sqlalchemy import delete, select

from bot.db.base import async_session_maker
from bot.db.models import Fixture, FavoriteLeague, League
from bot.keyboards.leagues import leagues_page_kb
from bot.services.notifier import cancel_notifications_for_fixtures

router = Router()


async def fetch_leagues_and_subs(user_id: int) -> tuple[list[League], set[int]]:
    async with async_session_maker() as session:
        leagues = (await session.execute(select(League).order_by(League.name))).scalars().all()
        subs = (
            await session.execute(select(FavoriteLeague.league_id).where(FavoriteLeague.user_id == user_id))
        ).scalars().all()
    return list(leagues), set(subs)


@router.callback_query(lambda c: c.data and c.data.startswith("leagues:"))
async def cb_leagues(query: CallbackQuery) -> None:
    page = int(query.data.split(":")[1])
    leagues, subs = await fetch_leagues_and_subs(query.from_user.id)
    text = "🏆 <b>Лиги</b> — нажми, чтобы подписаться/отписаться. ✅ — уже подписан."
    await query.message.edit_text(text, reply_markup=leagues_page_kb(leagues, page, subs, action="leagues"), parse_mode="HTML")
    await query.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("toggle_league:"))
async def cb_toggle_league(query: CallbackQuery) -> None:
    _, league_id_str, page_str = query.data.split(":")
    league_id = int(league_id_str)
    page = int(page_str)
    user_id = query.from_user.id

    async with async_session_maker() as session:
        existing = await session.scalar(
            select(FavoriteLeague).where(FavoriteLeague.user_id == user_id, FavoriteLeague.league_id == league_id)
        )
        if existing:
            await session.execute(
                delete(FavoriteLeague).where(FavoriteLeague.user_id == user_id, FavoriteLeague.league_id == league_id)
            )
            fixture_ids = list((await session.execute(
                select(Fixture.id).where(
                    Fixture.league_id == league_id,
                    Fixture.status.in_(["SCHEDULED", "LIVE"]),
                )
            )).scalars().all())
            await session.commit()
            await cancel_notifications_for_fixtures(user_id, fixture_ids)
            note = "Отписался от лиги"
        else:
            session.add(FavoriteLeague(user_id=user_id, league_id=league_id))
            await session.commit()
            note = "Подписался на лигу"

    leagues, subs = await fetch_leagues_and_subs(user_id)
    await query.message.edit_reply_markup(reply_markup=leagues_page_kb(leagues, page, subs, action="leagues"))
    await query.answer(note)
