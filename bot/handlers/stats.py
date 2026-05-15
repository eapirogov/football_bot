import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select

from bot.config import LEAGUE_ID_MAP
from bot.db.base import async_session_maker
from bot.db.models import Fixture, FixtureStatus, League, Team
from bot.services.football_api import current_season, football_api

router = Router()
log = logging.getLogger(__name__)

# обратный маппинг: числовой ID лиги → код football-data.org
_LEAGUE_CODE = {v: k for k, v in LEAGUE_ID_MAP.items()}


def _form_symbol(fixture: Fixture, team_id: int) -> str:
    """W/D/L для команды по завершённому матчу."""
    hs, as_ = fixture.home_score, fixture.away_score
    if hs is None or as_ is None:
        return "?"
    if fixture.home_team_id == team_id:
        if hs > as_:
            return "W"
        return "D" if hs == as_ else "L"
    else:
        if as_ > hs:
            return "W"
        return "D" if hs == as_ else "L"


async def _get_team_form(session, team_id: int, league_id: int) -> str:
    """Последние 5 завершённых матчей команды — строка вида WWDLW."""
    rows = (
        await session.execute(
            select(Fixture)
            .where(
                Fixture.league_id == league_id,
                Fixture.status == FixtureStatus.FINISHED,
                (Fixture.home_team_id == team_id) | (Fixture.away_team_id == team_id),
            )
            .order_by(Fixture.kickoff_utc.desc())
            .limit(5)
        )
    ).scalars().all()
    if not rows:
        return "нет данных"
    return "".join(_form_symbol(f, team_id) for f in reversed(rows))


async def _get_standing_pos(code: str, team_id: int) -> str:
    """Место команды в турнирной таблице."""
    table = await football_api.get_standings(code, current_season())
    for row in table:
        if (row.get("team") or {}).get("id") == team_id:
            pos = row.get("position", "?")
            pts = row.get("points", "?")
            played = row.get("playedGames", "?")
            return f"{pos}-е место, {pts} оч., {played} игр"
    return "нет данных"


@router.callback_query(F.data.startswith("stats:"))
async def cb_stats(query: CallbackQuery) -> None:
    fixture_id = int(query.data.split(":")[1])
    await query.answer("Загружаю итоги…")

    async with async_session_maker() as session:
        fixture = await session.get(Fixture, fixture_id)
        if not fixture:
            await query.message.answer("Не нашёл матч в базе.")
            return
        home = await session.get(Team, fixture.home_team_id)
        away = await session.get(Team, fixture.away_team_id)
        league = await session.get(League, fixture.league_id)

        home_form = await _get_team_form(session, home.id, fixture.league_id)
        away_form = await _get_team_form(session, away.id, fixture.league_id)

    score_home = fixture.home_score if fixture.home_score is not None else "?"
    score_away = fixture.away_score if fixture.away_score is not None else "?"
    score_line = f"<b>{home.name}</b> {score_home} — {score_away} <b>{away.name}</b>"

    league_name = league.name if league else ""
    code = _LEAGUE_CODE.get(fixture.league_id)

    home_standing = "—"
    away_standing = "—"
    if code and code not in ("WC", "EC"):  # у турниров нет таблицы группового этапа в простом виде
        try:
            home_standing = await _get_standing_pos(code, home.id)
            away_standing = await _get_standing_pos(code, away.id)
        except Exception:
            log.exception("failed to fetch standings for %s", code)

    text = (
        f"📊 <b>Итоги матча</b>\n"
        f"🏆 {league_name}\n\n"
        f"{score_line}\n\n"
        f"<b>Форма (последние 5):</b>  <i>W победа · D ничья · L поражение</i>\n"
        f"  {home.name}: {home_form}\n"
        f"  {away.name}: {away_form}\n\n"
        f"<b>В таблице:</b>\n"
        f"  {home.name}: {home_standing}\n"
        f"  {away.name}: {away_standing}"
    )
    await query.message.answer(text, parse_mode="HTML")
