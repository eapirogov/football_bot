import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bot.config import LEAGUE_CODES, LEAGUE_ID_MAP, settings
from bot.db.base import async_session_maker
from bot.db.models import (
    FavoriteLeague,
    FavoriteTeam,
    Fixture,
    FixtureStatus,
    Notification,
    NotificationKind,
    Team,
    UserSettings,
)
from bot.services.football_api import current_season, football_api

log = logging.getLogger(__name__)

# статусы football-data.org → наш enum
_STATUS_MAP = {
    "FINISHED": FixtureStatus.FINISHED,
    "IN_PLAY": FixtureStatus.LIVE,
    "PAUSED": FixtureStatus.LIVE,
    "POSTPONED": FixtureStatus.POSTPONED,
    "CANCELLED": FixtureStatus.POSTPONED,
    "SUSPENDED": FixtureStatus.POSTPONED,
}


def _parse_status(raw: str) -> FixtureStatus:
    return _STATUS_MAP.get(raw, FixtureStatus.SCHEDULED)


def _parse_score(match: dict) -> tuple[int | None, int | None]:
    score = match.get("score") or {}
    ft = score.get("fullTime") or {}
    return ft.get("home"), ft.get("away")


async def _upsert_fixture(session, match: dict, league_db_id: int) -> Fixture:
    kickoff = datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00"))
    status = _parse_status(match.get("status", "TIMED"))
    home_score, away_score = _parse_score(match)

    home_team = match["homeTeam"]
    away_team = match["awayTeam"]

    stmt = pg_insert(Fixture).values(
        id=match["id"],
        league_id=league_db_id,
        home_team_id=home_team["id"],
        away_team_id=away_team["id"],
        kickoff_utc=kickoff,
        status=status,
        home_score=home_score,
        away_score=away_score,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Fixture.id],
        set_={
            "kickoff_utc": stmt.excluded.kickoff_utc,
            "status": stmt.excluded.status,
            "home_score": stmt.excluded.home_score,
            "away_score": stmt.excluded.away_score,
        },
    )
    await session.execute(stmt)
    return await session.get(Fixture, match["id"])


async def _ensure_team(session, team_data: dict, league_id: int) -> None:
    if not team_data.get("id"):
        return
    stmt = pg_insert(Team).values(
        id=team_data["id"],
        name=team_data["name"] or team_data.get("shortName") or str(team_data["id"]),
        logo_url=team_data.get("crest"),
        league_id=league_id,
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=[Team.id])
    await session.execute(stmt)


async def _subscribers_for_fixture(session, fixture: Fixture) -> set[int]:
    by_team = (
        await session.execute(
            select(FavoriteTeam.user_id).where(
                FavoriteTeam.team_id.in_([fixture.home_team_id, fixture.away_team_id])
            )
        )
    ).scalars().all()
    by_league = (
        await session.execute(
            select(FavoriteLeague.user_id).where(FavoriteLeague.league_id == fixture.league_id)
        )
    ).scalars().all()
    return set(by_team) | set(by_league)


async def sync_fixtures(scheduler: AsyncIOScheduler | None = None, date_from_override: str | None = None) -> None:
    """Загружает матчи на ближайшие 7 дней, обновляет БД, планирует уведомления."""
    from bot.services.notifier import send_kickoff, send_post, send_pre  # local import to avoid cycle

    now = datetime.now(timezone.utc)
    date_from = date_from_override or now.date().isoformat()
    date_to = (now + timedelta(days=7)).date().isoformat()
    season = current_season()

    log.info("sync_fixtures: %s..%s, season=%s", date_from, date_to, season)
    sched = scheduler or _get_global_scheduler()

    async with async_session_maker() as session:
        for code in LEAGUE_CODES:
            league_db_id = LEAGUE_ID_MAP[code]
            try:
                matches = await football_api.get_matches(code, date_from, date_to, season)
            except Exception as exc:
                log.warning("Failed to fetch matches for %s: %s", code, exc)
                continue
            log.info("League %s: %d matches in window", code, len(matches))

            for match in matches:
                home_team = match.get("homeTeam") or {}
                away_team = match.get("awayTeam") or {}
                if not home_team.get("id") or not away_team.get("id"):
                    continue

                await _ensure_team(session, home_team, league_db_id)
                await _ensure_team(session, away_team, league_db_id)
                fixture = await _upsert_fixture(session, match, league_db_id)
                await session.commit()

                if fixture.status in (FixtureStatus.FINISHED, FixtureStatus.POSTPONED):
                    continue

                subs = await _subscribers_for_fixture(session, fixture)
                if not subs:
                    continue

                post_at = fixture.kickoff_utc + timedelta(minutes=settings.POST_MATCH_MINUTES)

                for user_id in subs:
                    # интервал напоминания у каждого свой (см. /settings), поэтому
                    # pre_at считается по его настройке, а не по общей константе
                    us = await session.get(UserSettings, user_id)
                    if us is not None and not us.notifications_enabled:
                        continue
                    pre_minutes = us.pre_match_minutes if us else settings.PRE_MATCH_MINUTES
                    pre_at = fixture.kickoff_utc - timedelta(minutes=pre_minutes)

                    if pre_at > now:
                        await _plan_notification(session, sched, user_id, fixture.id, NotificationKind.PRE, pre_at, send_pre)
                    if fixture.kickoff_utc > now:
                        await _plan_notification(session, sched, user_id, fixture.id, NotificationKind.KICKOFF, fixture.kickoff_utc, send_kickoff)
                    if post_at > now:
                        await _plan_notification(session, sched, user_id, fixture.id, NotificationKind.POST, post_at, send_post)
                await session.commit()


async def _plan_notification(session, scheduler, user_id: int, fixture_id: int, kind: NotificationKind, run_at, target) -> None:
    stmt = pg_insert(Notification).values(
        user_id=user_id, fixture_id=fixture_id, kind=kind.value, scheduled_at=run_at,
    ).on_conflict_do_nothing(index_elements=["user_id", "fixture_id", "kind"])
    await session.execute(stmt)
    await session.commit()

    notif = await session.scalar(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.fixture_id == fixture_id,
            Notification.kind == kind,
        )
    )
    if notif and notif.sent_at is None and scheduler is not None:
        job_id = f"notif:{notif.id}"
        if not scheduler.get_job(job_id):
            scheduler.add_job(
                target,
                "date",
                run_date=run_at,
                args=[notif.id],
                id=job_id,
                misfire_grace_time=600,
                replace_existing=True,
            )


async def reschedule_pending(scheduler: AsyncIOScheduler) -> None:
    """При старте бота подхватывает все неотправленные notifications из БД."""
    from bot.services.notifier import send_kickoff, send_post, send_pre

    now = datetime.now(timezone.utc)
    async with async_session_maker() as session:
        pending = (await session.execute(
            select(Notification).where(
                Notification.sent_at.is_(None),
                Notification.scheduled_at > now,
            )
        )).scalars().all()

    count = 0
    for notif in pending:
        job_id = f"notif:{notif.id}"
        if not scheduler.get_job(job_id):
            if notif.kind == NotificationKind.PRE:
                target = send_pre
            elif notif.kind == NotificationKind.KICKOFF:
                target = send_kickoff
            else:
                target = send_post
            scheduler.add_job(
                target,
                "date",
                run_date=notif.scheduled_at,
                args=[notif.id],
                id=job_id,
                misfire_grace_time=600,
                replace_existing=True,
            )
            count += 1
    if count:
        log.info("reschedule_pending: добавлено %d jobs", count)


_scheduler_ref: AsyncIOScheduler | None = None


def set_global_scheduler(scheduler: AsyncIOScheduler) -> None:
    global _scheduler_ref
    _scheduler_ref = scheduler


def _get_global_scheduler() -> AsyncIOScheduler | None:
    return _scheduler_ref
