import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.db.base import Base


class FixtureStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    LIVE = "LIVE"
    FINISHED = "FINISHED"
    POSTPONED = "POSTPONED"


class NotificationKind(str, enum.Enum):
    PRE = "pre"
    KICKOFF = "kickoff"
    POST = "post"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    favorite_teams: Mapped[list["FavoriteTeam"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    favorite_leagues: Mapped[list["FavoriteLeague"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    settings: Mapped["UserSettings | None"] = relationship(back_populates="user", cascade="all, delete-orphan", uselist=False)


class League(Base):
    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str] = mapped_column(String(64), nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    season: Mapped[int] = mapped_column(Integer, nullable=False)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))


class FavoriteTeam(Base):
    __tablename__ = "favorite_teams"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)

    user: Mapped[User] = relationship(back_populates="favorite_teams")
    team: Mapped[Team] = relationship()


class FavoriteLeague(Base):
    __tablename__ = "favorite_leagues"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"), primary_key=True)

    user: Mapped[User] = relationship(back_populates="favorite_leagues")
    league: Mapped[League] = relationship()


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Fixture(Base):
    __tablename__ = "fixtures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    venue_id: Mapped[int | None] = mapped_column(ForeignKey("venues.id", ondelete="SET NULL"), nullable=True)
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[FixtureStatus] = mapped_column(Enum(FixtureStatus), default=FixtureStatus.SCHEDULED)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)


class FixtureStatsCache(Base):
    __tablename__ = "fixture_stats_cache"

    fixture_id: Mapped[int] = mapped_column(
        ForeignKey("fixtures.id", ondelete="CASCADE"), primary_key=True
    )
    events_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    stats_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    pre_match_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Moscow")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="settings")


class StandingsCache(Base):
    __tablename__ = "standings_cache"

    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"), primary_key=True)
    season: Mapped[int] = mapped_column(Integer, primary_key=True)
    data_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "fixture_id", "kind", name="uq_user_fixture_kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id", ondelete="CASCADE"))
    kind: Mapped[NotificationKind] = mapped_column(
        Enum(NotificationKind, name="notificationkind", values_callable=lambda x: [e.value for e in x])
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
