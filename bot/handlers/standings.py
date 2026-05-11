from datetime import datetime, timezone, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot.config import LEAGUE_ID_MAP, SEASONLESS_CODES
from bot.db.base import async_session_maker
from bot.db.models import League, StandingsCache
from bot.services.football_api import current_season, football_api

router = Router()

STANDINGS_TTL_HOURS = 2

# лиги без турнирной таблицы (плей-офф / сборные)
_NO_TABLE = {"WC", "EC", "CL"}
_TABLE_CODES = [code for code in LEAGUE_ID_MAP if code not in _NO_TABLE]


async def _get_standings(league_id: int, code: str) -> list[dict]:
    season = None if code in SEASONLESS_CODES else current_season()
    season_key = season or 0

    async with async_session_maker() as session:
        cached = await session.get(StandingsCache, (league_id, season_key))
        if cached:
            age = datetime.now(timezone.utc) - cached.updated_at.replace(tzinfo=timezone.utc)
            if age < timedelta(hours=STANDINGS_TTL_HOURS):
                return cached.data_json

        rows = await football_api.get_standings(code, season)
        if not rows:
            return []

        if cached:
            cached.data_json = rows
            cached.updated_at = datetime.now(timezone.utc)
        else:
            session.add(StandingsCache(league_id=league_id, season=season_key, data_json=rows))
        await session.commit()
        return rows


def _format_table(rows: list[dict], full: bool = False) -> str:
    limit = len(rows) if full else min(10, len(rows))
    lines = ["<pre>"]
    lines.append(" #  Команда                И   В  Н  П   О")
    lines.append("─" * 46)
    for row in rows[:limit]:
        pos = row.get("position", "")
        team = (row.get("team") or {}).get("shortName") or (row.get("team") or {}).get("name") or "?"
        team = team[:20].ljust(20)
        played = row.get("playedGames", 0)
        won = row.get("won", 0)
        draw = row.get("draw", 0)
        lost = row.get("lost", 0)
        pts = row.get("points", 0)
        lines.append(f"{str(pos).rjust(2)}  {team}  {str(played).rjust(2)}  {str(won).rjust(2)} {str(draw).rjust(2)} {str(lost).rjust(2)}  {str(pts).rjust(3)}")
    lines.append("</pre>")
    return "\n".join(lines)


async def _league_select_kb() -> InlineKeyboardMarkup:
    async with async_session_maker() as session:
        leagues = (
            await session.execute(
                select(League).where(League.id.in_([LEAGUE_ID_MAP[c] for c in _TABLE_CODES]))
                .order_by(League.name)
            )
        ).scalars().all()

    buttons = [
        [InlineKeyboardButton(text=lg.name, callback_data=f"standings:{lg.id}:0")]
        for lg in leagues
    ]
    buttons.append([InlineKeyboardButton(text="🏠 В меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _render_standings(league_id: int, full: bool) -> tuple[str, InlineKeyboardMarkup]:
    async with async_session_maker() as session:
        league = await session.get(League, league_id)

    if not league:
        return "Лига не найдена.", InlineKeyboardMarkup(inline_keyboard=[])

    code = next((c for c, lid in LEAGUE_ID_MAP.items() if lid == league_id), None)
    if not code:
        return "Лига не поддерживается.", InlineKeyboardMarkup(inline_keyboard=[])

    rows = await _get_standings(league_id, code)
    if not rows:
        text = f"📊 <b>{league.name}</b>\n\nТаблица пока недоступна."
    else:
        header = f"📊 <b>{league.name}</b> — сезон {league.season}/{league.season + 1 if league.season >= 2000 else ''}\n\n"
        text = header + _format_table(rows, full=full)

    toggle_label = "▲ Свернуть" if full else "▼ Показать всю"
    toggle_cb = f"standings:{league_id}:{0 if full else 1}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_label, callback_data=toggle_cb)],
        [InlineKeyboardButton(text="◀ К списку лиг", callback_data="standings:list")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
    ])
    return text, kb


@router.message(Command("table"))
async def cmd_table(message: Message) -> None:
    kb = await _league_select_kb()
    await message.answer("📊 <b>Турнирные таблицы</b>\n\nВыбери лигу:", reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "standings:list")
async def cb_standings_list(query: CallbackQuery) -> None:
    kb = await _league_select_kb()
    await query.message.edit_text("📊 <b>Турнирные таблицы</b>\n\nВыбери лигу:", reply_markup=kb, parse_mode="HTML")
    await query.answer()


@router.callback_query(F.data.startswith("standings:") & ~F.data.endswith(":list"))
async def cb_standings(query: CallbackQuery) -> None:
    parts = query.data.split(":")
    if len(parts) != 3:
        await query.answer()
        return
    league_id = int(parts[1])
    full = parts[2] == "1"
    text, kb = await _render_standings(league_id, full)
    await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await query.answer()
