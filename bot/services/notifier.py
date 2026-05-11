import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from bot.db.base import async_session_maker
from bot.db.models import Fixture, FixtureStatus, League, Notification, Team, UserSettings

log = logging.getLogger(__name__)

_bot_ref: Bot | None = None


def set_bot(bot: Bot) -> None:
    global _bot_ref
    _bot_ref = bot


def _bot() -> Bot:
    if _bot_ref is None:
        raise RuntimeError("Notifier bot is not initialized")
    return _bot_ref


async def _load(notification_id: int):
    async with async_session_maker() as session:
        notif = await session.get(Notification, notification_id)
        if not notif:
            return None, None, None, None, None, None
        fixture = await session.get(Fixture, notif.fixture_id)
        league = await session.get(League, fixture.league_id) if fixture else None
        home = await session.get(Team, fixture.home_team_id) if fixture else None
        away = await session.get(Team, fixture.away_team_id) if fixture else None
        user_settings = await session.get(UserSettings, notif.user_id)
        return notif, fixture, league, home, away, user_settings


async def _mark_sent(notification_id: int) -> None:
    async with async_session_maker() as session:
        notif = await session.get(Notification, notification_id)
        if notif:
            notif.sent_at = datetime.now(timezone.utc)
            await session.commit()


def _reschedule(notification_id: int, target, delay_seconds: int) -> None:
    from bot.services.fixtures_sync import _get_global_scheduler
    scheduler = _get_global_scheduler()
    if scheduler is None:
        return
    run_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
    job_id = f"notif:{notification_id}:retry"
    scheduler.add_job(
        target,
        "date",
        run_date=run_at,
        args=[notification_id],
        id=job_id,
        replace_existing=True,
        misfire_grace_time=120,
    )
    log.info("rescheduled notif=%s in %ds", notification_id, delay_seconds)


async def send_pre(notification_id: int) -> None:
    notif, fixture, league, home, away, user_settings = await _load(notification_id)
    if not notif or notif.sent_at or not fixture:
        return
    if user_settings and not user_settings.notifications_enabled:
        log.info("send_pre skipped: notifications disabled for user=%s", notif.user_id)
        return

    from bot.utils.time import fmt_user_tz
    tz = user_settings.timezone if user_settings else "Europe/Moscow"
    local = fmt_user_tz(fixture.kickoff_utc, tz)
    league_name = league.name if league else ""
    text = (
        "⚽  <b>СКОРО МАТЧ</b>\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"🏆  {league_name}\n\n"
        f"🔵  <b>{home.name}</b>\n"
        f"⚪  <b>{away.name}</b>\n\n"
        f"🕐  Начало в <b>{local}</b>"
    )
    try:
        await _bot().send_message(notif.user_id, text, parse_mode="HTML")
        await _mark_sent(notification_id)
        log.info("sent pre for notif=%s (fixture=%s)", notification_id, fixture.id)
    except TelegramRetryAfter as exc:
        log.warning("send_pre flood notif=%s, retry in %ds", notification_id, exc.retry_after)
        _reschedule(notification_id, send_pre, exc.retry_after + 5)
    except TelegramNetworkError as exc:
        log.warning("send_pre network error notif=%s: %s, retry in 30s", notification_id, exc)
        _reschedule(notification_id, send_pre, 30)
    except TelegramForbiddenError:
        log.info("send_pre blocked by user=%s, marking sent", notif.user_id)
        await _mark_sent(notification_id)
    except Exception as exc:
        log.warning("send_pre failed for notif=%s: %s", notification_id, exc)


async def send_kickoff(notification_id: int) -> None:
    notif, fixture, league, home, away, user_settings = await _load(notification_id)
    if not notif or notif.sent_at or not fixture:
        return
    if user_settings and not user_settings.notifications_enabled:
        log.info("send_kickoff skipped: notifications disabled for user=%s", notif.user_id)
        return

    league_name = league.name if league else ""
    text = (
        "🟢  <b>МАТЧ НАЧАЛСЯ</b>\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"🏆  {league_name}\n\n"
        f"🔵  <b>{home.name}</b>\n"
        f"⚪  <b>{away.name}</b>"
    )
    try:
        await _bot().send_message(notif.user_id, text, parse_mode="HTML")
        await _mark_sent(notification_id)
        log.info("sent kickoff for notif=%s (fixture=%s)", notification_id, fixture.id)
    except TelegramRetryAfter as exc:
        log.warning("send_kickoff flood notif=%s, retry in %ds", notification_id, exc.retry_after)
        _reschedule(notification_id, send_kickoff, exc.retry_after + 5)
    except TelegramNetworkError as exc:
        log.warning("send_kickoff network error notif=%s: %s, retry in 30s", notification_id, exc)
        _reschedule(notification_id, send_kickoff, 30)
    except TelegramForbiddenError:
        log.info("send_kickoff blocked by user=%s, marking sent", notif.user_id)
        await _mark_sent(notification_id)
    except Exception as exc:
        log.warning("send_kickoff failed for notif=%s: %s", notification_id, exc)


async def send_post(notification_id: int) -> None:
    notif, fixture, league, home, away, user_settings = await _load(notification_id)
    if not notif or notif.sent_at or not fixture:
        return

    # если матч ещё не завершён по данным БД — пропускаем (sync_fixtures обновит позже)
    if user_settings and not user_settings.notifications_enabled:
        log.info("send_post skipped: notifications disabled for user=%s", notif.user_id)
        return
    if fixture.status != FixtureStatus.FINISHED:
        log.info("Fixture %s not finished yet (%s) — skip post", fixture.id, fixture.status)
        return

    score_home = fixture.home_score if fixture.home_score is not None else "?"
    score_away = fixture.away_score if fixture.away_score is not None else "?"
    league_name = league.name if league else ""
    text = (
        "🔴  <b>МАТЧ ЗАВЕРШЁН</b>\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"🏆  {league_name}\n\n"
        f"🔵  <b>{home.name}</b>\n"
        f"⚪  <b>{away.name}</b>\n\n"
        f"⚽  Счёт: <b>{score_home} — {score_away}</b>"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📊 Итоги", callback_data=f"stats:{fixture.id}")]]
    )
    try:
        await _bot().send_message(notif.user_id, text, reply_markup=kb, parse_mode="HTML")
        await _mark_sent(notification_id)
        log.info("sent post for notif=%s (fixture=%s)", notification_id, fixture.id)
    except TelegramRetryAfter as exc:
        log.warning("send_post flood notif=%s, retry in %ds", notification_id, exc.retry_after)
        _reschedule(notification_id, send_post, exc.retry_after + 5)
    except TelegramNetworkError as exc:
        log.warning("send_post network error notif=%s: %s, retry in 30s", notification_id, exc)
        _reschedule(notification_id, send_post, 30)
    except TelegramForbiddenError:
        log.info("send_post blocked by user=%s, marking sent", notif.user_id)
        await _mark_sent(notification_id)
    except Exception as exc:
        log.warning("send_post failed for notif=%s: %s", notification_id, exc)
