from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import settings


def _sync_db_url() -> str:
    """APScheduler's SQLAlchemyJobStore needs a sync driver."""
    url = settings.DATABASE_URL
    return url.replace("postgresql+asyncpg://", "postgresql://").replace("+asyncpg", "")


def build_scheduler() -> AsyncIOScheduler:
    jobstores = {"default": SQLAlchemyJobStore(url=_sync_db_url())}
    scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=settings.TIMEZONE)
    return scheduler
