"""Plant a demo fixture and schedule pre/post notifications.

Берёт первые две команды из БД, создаёт фиктивный матч с kickoff через ~90 секунд,
планирует PRE (через 60с) и POST (через 5 минут) для всех подписчиков.

Usage: python -m seeds.demo_fixture [--pre-sec 60] [--post-sec 300]
"""
import argparse
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bot.db.base import async_session_maker
from bot.db.models import (
    FavoriteLeague,
    FavoriteTeam,
    Fixture,
    FixtureStatus,
    League,
    Notification,
    NotificationKind,
    Team,
)
from bot.services.scheduler import build_scheduler
from bot.services.notifier import send_pre, send_post

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("demo_fixture")

DEMO_FIXTURE_ID = 999999999


async def main(pre_sec: int, post_sec: int) -> None:
    async with async_session_maker() as session:
        # берём любую лигу и две команды из неё
        league = (await session.execute(select(League).limit(1))).scalar_one_or_none()
        if not league:
            log.error("Нет лиг в БД — сначала запусти seeds.leagues_teams")
            return

        teams = (
            await session.execute(select(Team).where(Team.league_id == league.id).limit(2))
        ).scalars().all()
        if len(teams) < 2:
            log.error("Нет команд в БД — сначала запусти seeds.leagues_teams")
            return

        home, away = teams[0], teams[1]
        now = datetime.now(timezone.utc)
        kickoff = now + timedelta(seconds=pre_sec + 30)
        pre_at = now + timedelta(seconds=pre_sec)
        post_at = now + timedelta(seconds=post_sec)

        stmt = pg_insert(Fixture).values(
            id=DEMO_FIXTURE_ID,
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_utc=kickoff,
            status=FixtureStatus.SCHEDULED,
            home_score=None,
            away_score=None,
        ).on_conflict_do_update(
            index_elements=[Fixture.id],
            set_={
                "kickoff_utc": kickoff,
                "status": FixtureStatus.SCHEDULED,
                "home_score": None,
                "away_score": None,
            },
        )
        await session.execute(stmt)
        await session.commit()
        log.info("Fixture: %s — %s, kickoff %s UTC", home.name, away.name, kickoff.isoformat())

        # находим подписчиков
        by_team = (await session.execute(
            select(FavoriteTeam.user_id).where(FavoriteTeam.team_id.in_([home.id, away.id]))
        )).scalars().all()
        by_league = (await session.execute(
            select(FavoriteLeague.user_id).where(FavoriteLeague.league_id == league.id)
        )).scalars().all()
        subs = set(by_team) | set(by_league)

        if not subs:
            log.warning("Нет подписчиков — подпишись на лигу '%s' или команду в боте, потом запусти снова", league.name)
            return
        log.info("Подписчики: %s", subs)

        notif_jobs: list[tuple[int, NotificationKind, datetime]] = []
        for user_id in subs:
            for kind, sched_at in ((NotificationKind.PRE, pre_at), (NotificationKind.POST, post_at)):
                ins = pg_insert(Notification).values(
                    user_id=user_id, fixture_id=DEMO_FIXTURE_ID, kind=kind.value, scheduled_at=sched_at,
                ).on_conflict_do_update(
                    index_elements=["user_id", "fixture_id", "kind"],
                    set_={"scheduled_at": sched_at, "sent_at": None},
                )
                await session.execute(ins)
                await session.commit()
                notif = await session.scalar(
                    select(Notification).where(
                        Notification.user_id == user_id,
                        Notification.fixture_id == DEMO_FIXTURE_ID,
                        Notification.kind == kind,
                    )
                )
                if notif:
                    notif_jobs.append((notif.id, kind, sched_at))

    scheduler = build_scheduler()
    scheduler.start(paused=True)
    try:
        for notif_id, kind, sched_at in notif_jobs:
            target = send_pre if kind == NotificationKind.PRE else send_post
            scheduler.add_job(
                target,
                "date",
                run_date=sched_at,
                args=[notif_id],
                id=f"notif:{notif_id}",
                replace_existing=True,
                misfire_grace_time=600,
            )
        log.info("Запланировано %d уведомлений", len(notif_jobs))
        log.info("PRE через %ds, POST через %ds", pre_sec, post_sec)
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--pre-sec", type=int, default=60)
    p.add_argument("--post-sec", type=int, default=300)
    args = p.parse_args()
    asyncio.run(main(args.pre_sec, args.post_sec))
