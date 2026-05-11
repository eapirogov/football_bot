from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bot.config import settings

MSK = ZoneInfo(settings.TIMEZONE)


def to_msk(dt_utc: datetime) -> datetime:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=ZoneInfo("UTC"))
    return dt_utc.astimezone(MSK)


def fmt_msk(dt_utc: datetime) -> str:
    return to_msk(dt_utc).strftime("%d.%m %H:%M МСК")


def fmt_user_tz(dt_utc: datetime, tz_name: str) -> str:
    """Форматирует время в часовом поясе пользователя."""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=ZoneInfo("UTC"))
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError):
        tz = MSK
    local = dt_utc.astimezone(tz)
    offset = local.utcoffset()
    hours = int(offset.total_seconds() // 3600) if offset else 0
    sign = "+" if hours >= 0 else ""
    return local.strftime(f"%d.%m %H:%M (UTC{sign}{hours})")
