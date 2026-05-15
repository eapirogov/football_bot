from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import delete, select

from bot.db.base import async_session_maker
from bot.db.models import Fixture, FavoriteTeam, League, Team
from bot.keyboards.leagues import leagues_page_kb
from bot.keyboards.teams import teams_page_kb
from bot.services.notifier import cancel_notifications_for_fixtures
from bot.states.fsm import TeamSearch

router = Router()


async def fetch_user_team_subs(user_id: int) -> set[int]:
    async with async_session_maker() as session:
        rows = (
            await session.execute(select(FavoriteTeam.team_id).where(FavoriteTeam.user_id == user_id))
        ).scalars().all()
    return set(rows)


@router.callback_query(F.data.startswith("teams_leagues:"))
async def cb_teams_leagues(query: CallbackQuery) -> None:
    page = int(query.data.split(":")[1])
    async with async_session_maker() as session:
        leagues = (await session.execute(select(League).order_by(League.name))).scalars().all()
    await query.message.edit_text(
        "⚽ Выбери лигу, чтобы посмотреть её команды:",
        reply_markup=leagues_page_kb(list(leagues), page, set(), action="pick_league"),
    )
    await query.answer()


@router.callback_query(F.data.startswith("open_league_teams:"))
async def cb_open_league_teams(query: CallbackQuery) -> None:
    _, league_id_str, page_str = query.data.split(":")
    league_id = int(league_id_str)
    page = int(page_str)

    async with async_session_maker() as session:
        league = await session.get(League, league_id)
        teams = (
            await session.execute(select(Team).where(Team.league_id == league_id).order_by(Team.name))
        ).scalars().all()
    subs = await fetch_user_team_subs(query.from_user.id)
    title = f"⚽ <b>{league.name}</b> — команды:" if league else "⚽ Команды:"
    await query.message.edit_text(
        title,
        reply_markup=teams_page_kb(league_id, list(teams), page, subs),
        parse_mode="HTML",
    )
    await query.answer()


@router.callback_query(F.data.startswith("toggle_team:"))
async def cb_toggle_team(query: CallbackQuery) -> None:
    _, team_id_str, league_id_str, page_str = query.data.split(":")
    team_id = int(team_id_str)
    league_id = int(league_id_str)
    page = int(page_str)
    user_id = query.from_user.id

    async with async_session_maker() as session:
        existing = await session.scalar(
            select(FavoriteTeam).where(FavoriteTeam.user_id == user_id, FavoriteTeam.team_id == team_id)
        )
        if existing:
            await session.execute(
                delete(FavoriteTeam).where(FavoriteTeam.user_id == user_id, FavoriteTeam.team_id == team_id)
            )
            fixture_ids = list((await session.execute(
                select(Fixture.id).where(
                    Fixture.status.in_(["SCHEDULED", "LIVE"]),
                    (Fixture.home_team_id == team_id) | (Fixture.away_team_id == team_id),
                )
            )).scalars().all())
            await session.commit()
            await cancel_notifications_for_fixtures(user_id, fixture_ids)
            note = "Отписался от команды"
        else:
            session.add(FavoriteTeam(user_id=user_id, team_id=team_id))
            await session.commit()
            note = "Подписался на команду"

        teams = (
            await session.execute(select(Team).where(Team.league_id == league_id).order_by(Team.name))
        ).scalars().all()
    subs = await fetch_user_team_subs(user_id)
    await query.message.edit_reply_markup(reply_markup=teams_page_kb(league_id, list(teams), page, subs))
    await query.answer(note)


@router.callback_query(F.data == "search_team")
async def cb_search_team(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TeamSearch.waiting_for_query)
    await query.message.answer("🔍 Введи часть названия команды:")
    await query.answer()


@router.message(TeamSearch.waiting_for_query)
async def receive_team_query(message: Message, state: FSMContext) -> None:
    q = (message.text or "").strip()
    await state.clear()
    if len(q) < 2:
        await message.answer("Слишком короткий запрос — введи минимум 2 символа.")
        return

    async with async_session_maker() as session:
        teams = (
            await session.execute(
                select(Team).where(Team.name.ilike(f"%{q}%")).order_by(Team.name).limit(20)
            )
        ).scalars().all()

    if not teams:
        await message.answer("❌ Ничего не нашёл. Попробуй другое название.")
        return

    subs = await fetch_user_team_subs(message.from_user.id)
    rows = [
        [InlineKeyboardButton(
            text=("✅ " if t.id in subs else "") + f"{t.name}",
            callback_data=f"toggle_team_search:{t.id}",
        )]
        for t in teams
    ]
    rows.append([InlineKeyboardButton(text="🏠 В меню", callback_data="menu")])
    await message.answer(f"Нашёл по запросу «{q}»:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("toggle_team_search:"))
async def cb_toggle_team_from_search(query: CallbackQuery) -> None:
    team_id = int(query.data.split(":")[1])
    user_id = query.from_user.id
    async with async_session_maker() as session:
        existing = await session.scalar(
            select(FavoriteTeam).where(FavoriteTeam.user_id == user_id, FavoriteTeam.team_id == team_id)
        )
        if existing:
            await session.execute(
                delete(FavoriteTeam).where(FavoriteTeam.user_id == user_id, FavoriteTeam.team_id == team_id)
            )
            fixture_ids = list((await session.execute(
                select(Fixture.id).where(
                    Fixture.status.in_(["SCHEDULED", "LIVE"]),
                    (Fixture.home_team_id == team_id) | (Fixture.away_team_id == team_id),
                )
            )).scalars().all())
            await session.commit()
            await cancel_notifications_for_fixtures(user_id, fixture_ids)
            await query.answer("Отписался")
        else:
            session.add(FavoriteTeam(user_id=user_id, team_id=team_id))
            await session.commit()
            await query.answer("Подписался")
