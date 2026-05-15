import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.handlers import calendar, favorites, leagues, start, standings, stats, teams
from bot.handlers import settings as settings_handler
from bot.services import notifier
from bot.services.fixtures_sync import reschedule_pending, set_global_scheduler, sync_fixtures
from bot.services.scheduler import build_scheduler


async def main() -> None:
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    log = logging.getLogger("bot")

    from bot.services.football_api import football_api
    key_last4 = settings.FOOTBALL_DATA_KEY[-4:] if len(settings.FOOTBALL_DATA_KEY) >= 4 else "****"
    log.info("Checking football-data.org API key (****%s)…", key_last4)
    if not await football_api.check_api_key():
        log.error("football-data.org API key is invalid or lacks permissions. Check FOOTBALL_DATA_KEY in .env")
        return

    bot = Bot(token=settings.TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    from bot.middleware import UpsertUserMiddleware
    dp.message.middleware(UpsertUserMiddleware())
    dp.callback_query.middleware(UpsertUserMiddleware())

    dp.include_router(start.router)
    dp.include_router(leagues.router)
    dp.include_router(teams.router)
    dp.include_router(favorites.router)
    dp.include_router(stats.router)
    dp.include_router(settings_handler.router)
    dp.include_router(calendar.router)
    dp.include_router(standings.router)

    from aiogram.types import BotCommand
    await bot.set_my_commands([
        BotCommand(command="start",    description="Главное меню"),
        BotCommand(command="upcoming", description="Ближайшие матчи"),
        BotCommand(command="results",  description="Последние результаты"),
        BotCommand(command="table",    description="Турнирные таблицы"),
        BotCommand(command="settings", description="Настройки"),
        BotCommand(command="help",     description="Помощь"),
    ])

    notifier.set_bot(bot)

    scheduler = build_scheduler()
    set_global_scheduler(scheduler)
    scheduler.add_job(
        sync_fixtures,
        "interval",
        hours=settings.SYNC_INTERVAL_HOURS,
        id="sync_fixtures_loop",
        replace_existing=True,
        misfire_grace_time=600,
    )
    scheduler.start()

    from datetime import datetime, timedelta, timezone as _tz
    catchup_from = (datetime.now(_tz.utc) - timedelta(days=30)).date().isoformat()
    asyncio.create_task(sync_fixtures(scheduler, date_from_override=catchup_from))
    await reschedule_pending(scheduler)

    log.info("=" * 50)
    log.info("⚽ Football bot started — listening for updates")
    log.info("=" * 50)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
