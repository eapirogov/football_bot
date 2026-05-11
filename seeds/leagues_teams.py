"""One-time seed: pull leagues and teams from football-data.org into local DB.

Run: python -m seeds.leagues_teams
"""
import asyncio
import logging

from sqlalchemy.dialects.postgresql import insert as pg_insert

from bot.config import LEAGUE_CODES, LEAGUE_ID_MAP, SEASONLESS_CODES
from bot.db.base import async_session_maker
from bot.db.models import League, Team
from bot.services.football_api import current_season, football_api

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed")

# названия лиг и страны — получаем из API
_LEAGUE_COUNTRY = {
    "PL":  "England",
    "PD":  "Spain",
    "SA":  "Italy",
    "BL1": "Germany",
    "FL1": "France",
    "CL":  "Europe",
    "WC":  "World",
    "EC":  "Europe",
    "ELC": "England",
    "DED": "Netherlands",
    "PPL": "Portugal",
    "BSA": "Brazil",
}


async def seed() -> None:
    season = current_season()
    log.info("Seeding for season %s", season)

    async with async_session_maker() as session:
        for code in LEAGUE_CODES:
            league_db_id = LEAGUE_ID_MAP[code]

            comp = await football_api.get_competition(code)
            if not comp:
                log.warning("Competition %s not found", code)
                continue

            league_name = comp.get("name") or code
            country = _LEAGUE_COUNTRY.get(code, "")
            logo_url = (comp.get("emblem") or comp.get("area", {}).get("flag"))

            stmt = pg_insert(League).values(
                id=league_db_id,
                name=league_name,
                country=country,
                logo_url=logo_url,
                season=season,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[League.id],
                set_={"name": stmt.excluded.name, "season": stmt.excluded.season, "logo_url": stmt.excluded.logo_url},
            )
            await session.execute(stmt)
            log.info("League %s (%s) saved", league_name, country)

            teams_season = None if code in SEASONLESS_CODES else season
            teams = await football_api.get_teams(code, teams_season)
            for team in teams:
                stmt = pg_insert(Team).values(
                    id=team["id"],
                    name=team.get("name") or team.get("shortName") or str(team["id"]),
                    country=team.get("area", {}).get("name"),
                    logo_url=team.get("crest"),
                    league_id=league_db_id,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=[Team.id],
                    set_={"name": stmt.excluded.name, "logo_url": stmt.excluded.logo_url},
                )
                await session.execute(stmt)
            await session.commit()
            log.info("  -> %d teams saved for %s", len(teams), code)

    log.info("Seed complete")


if __name__ == "__main__":
    asyncio.run(seed())
