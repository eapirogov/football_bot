from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import or_, select

from bot.db.base import async_session_maker
from bot.db.models import Fixture, FixtureStatus, FavoriteLeague, FavoriteTeam, League, Team, UserSettings
from bot.utils.time import fmt_user_tz

router = Router()

LEAGUE_FLAGS = {
    "England":     "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Spain":       "🇪🇸",
    "Germany":     "🇩🇪",
    "Italy":       "🇮🇹",
    "France":      "🇫🇷",
    "Europe":      "🇪🇺",
    "World":       "🌍",
    "Netherlands": "🇳🇱",
    "Portugal":    "🇵🇹",
    "Brazil":      "🇧🇷",
}


def _flag(country: str) -> str:
    return LEAGUE_FLAGS.get(country, "🏆")


def _format_fixture(f: Fixture, home: Team, away: Team, league: League, tz: str) -> str:
    date_str = fmt_user_tz(f.kickoff_utc, tz)
    flag = _flag(league.country)
    if f.status == FixtureStatus.FINISHED and f.home_score is not None:
        score = f"<b>{f.home_score} : {f.away_score}</b>"
        return f"{flag}  {date_str}\n<b>{home.name}</b>  {score}  <b>{away.name}</b>"
    return f"{flag}  {date_str}\n<b>{home.name}</b>  —  <b>{away.name}</b>"


async def _get_subscribed_fixture_ids(session, user_id: int) -> tuple[set[int], set[int]]:
    """Возвращает (team_ids, league_ids) подписок пользователя."""
    team_ids = set(
        (await session.execute(
            select(FavoriteTeam.team_id).where(FavoriteTeam.user_id == user_id)
        )).scalars().all()
    )
    league_ids = set(
        (await session.execute(
            select(FavoriteLeague.league_id).where(FavoriteLeague.league_id != None, FavoriteLeague.user_id == user_id)
        )).scalars().all()
    )
    return team_ids, league_ids


async def _fetch_fixtures(user_id: int, statuses: list[FixtureStatus], limit: int, asc: bool) -> list[str]:
    now = datetime.now(timezone.utc)
    async with async_session_maker() as session:
        team_ids, league_ids = await _get_subscribed_fixture_ids(session, user_id)
        if not team_ids and not league_ids:
            return []

        user_settings = await session.get(UserSettings, user_id)
        tz = user_settings.timezone if user_settings else "Europe/Moscow"

        order = Fixture.kickoff_utc.asc() if asc else Fixture.kickoff_utc.desc()
        rows = (await session.execute(
            select(Fixture)
            .where(
                Fixture.status.in_(statuses),
                or_(
                    Fixture.home_team_id.in_(team_ids),
                    Fixture.away_team_id.in_(team_ids),
                    Fixture.league_id.in_(league_ids),
                ) if (team_ids or league_ids) else False,
                Fixture.kickoff_utc > now if asc else Fixture.kickoff_utc <= now,
            )
            .order_by(order)
            .limit(limit)
        )).scalars().all()

        lines = []
        for f in rows:
            home = await session.get(Team, f.home_team_id)
            away = await session.get(Team, f.away_team_id)
            league = await session.get(League, f.league_id)
            if home and away and league:
                lines.append(_format_fixture(f, home, away, league, tz))
        return lines


async def _render_upcoming(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    lines = await _fetch_fixtures(
        user_id,
        statuses=[FixtureStatus.SCHEDULED, FixtureStatus.LIVE],
        limit=8,
        asc=True,
    )
    if not lines:
        text = "📅 Нет предстоящих матчей по твоим подпискам.\n\nПодпишись на лиги или команды в меню."
    else:
        text = "📅 <b>Ближайшие матчи</b>\n\n" + "\n\n".join(lines)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Последние результаты", callback_data="calendar:results")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
    ])
    return text, kb


async def _render_results(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    lines = await _fetch_fixtures(
        user_id,
        statuses=[FixtureStatus.FINISHED],
        limit=8,
        asc=False,
    )
    if not lines:
        text = "📋 Нет завершённых матчей по твоим подпискам."
    else:
        text = "📋 <b>Последние результаты</b>\n\n" + "\n\n".join(lines)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Ближайшие матчи", callback_data="calendar:upcoming")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
    ])
    return text, kb


@router.message(Command("upcoming"))
async def cmd_upcoming(message: Message) -> None:
    text, kb = await _render_upcoming(message.from_user.id)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(Command("results"))
async def cmd_results(message: Message) -> None:
    text, kb = await _render_results(message.from_user.id)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "calendar:upcoming")
async def cb_upcoming(query: CallbackQuery) -> None:
    text, kb = await _render_upcoming(query.from_user.id)
    await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await query.answer()


@router.callback_query(F.data == "calendar:results")
async def cb_results(query: CallbackQuery) -> None:
    text, kb = await _render_results(query.from_user.id)
    await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await query.answer()
