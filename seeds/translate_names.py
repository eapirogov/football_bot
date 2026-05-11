"""Переводит названия команд и лиг в БД на русский через Google Translate."""
import asyncio
import logging
import time

from deep_translator import GoogleTranslator
from sqlalchemy import select, update

from bot.db.base import async_session_maker
from bot.db.models import League, Team

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

translator = GoogleTranslator(source="en", target="ru")

_LEAGUE_OVERRIDES = {
    "UEFA Champions League": "Лига чемпионов УЕФА",
    "UEFA Europa League": "Лига Европы УЕФА",
    "FIFA World Cup": "Чемпионат мира FIFA",
    "European Championship": "Чемпионат Европы",
    "Premier League": "Премьер-лига",
    "Bundesliga": "Бундеслига",
    "Serie A": "Серия А",
    "Ligue 1": "Лига 1",
    "Primera Division": "Ла Лига",
    "Championship": "Чемпионшип",
    "Russian Premier League": "РПЛ",
}


def _translate(name: str) -> str:
    if name in _LEAGUE_OVERRIDES:
        return _LEAGUE_OVERRIDES[name]
    try:
        result = translator.translate(name)
        return result or name
    except Exception as exc:
        log.warning("translate failed for %r: %s", name, exc)
        return name


def _looks_russian(name: str) -> bool:
    return any("Ѐ" <= ch <= "ӿ" for ch in name)


async def translate_leagues() -> None:
    async with async_session_maker() as session:
        leagues = (await session.execute(select(League))).scalars().all()
        count = 0
        for lg in leagues:
            if _looks_russian(lg.name):
                continue
            ru = _translate(lg.name)
            if ru != lg.name:
                lg.name = ru
                count += 1
                log.info("league: %s → %s", lg.name, ru)
        await session.commit()
    log.info("translated %d leagues", count)


async def translate_teams() -> None:
    async with async_session_maker() as session:
        teams = (await session.execute(select(Team))).scalars().all()

    to_translate = [t for t in teams if not _looks_russian(t.name)]
    log.info("teams to translate: %d", len(to_translate))

    batch_size = 50
    for i in range(0, len(to_translate), batch_size):
        batch = to_translate[i:i + batch_size]
        names = [t.name for t in batch]
        try:
            translated = translator.translate_batch(names)
        except Exception as exc:
            log.warning("batch translate failed: %s, falling back one by one", exc)
            translated = [_translate(n) for n in names]
            time.sleep(1)

        async with async_session_maker() as session:
            for team, ru in zip(batch, translated):
                if ru and ru != team.name:
                    await session.execute(
                        update(Team).where(Team.id == team.id).values(name=ru)
                    )
                    log.info("team: %s → %s", team.name, ru)
            await session.commit()

        log.info("batch %d/%d done", i + batch_size, len(to_translate))
        time.sleep(0.5)  # не флудить Google


async def main() -> None:
    await translate_leagues()
    await translate_teams()
    log.info("done")


if __name__ == "__main__":
    asyncio.run(main())
