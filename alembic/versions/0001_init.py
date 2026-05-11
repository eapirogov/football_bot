"""init schema

Revision ID: 0001_init
Revises:
Create Date: 2026-05-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


fixture_status = sa.Enum("SCHEDULED", "LIVE", "FINISHED", "POSTPONED", name="fixturestatus")
notification_kind = sa.Enum("pre", "post", name="notificationkind")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "leagues",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("country", sa.String(64), nullable=False),
        sa.Column("logo_url", sa.String(255), nullable=True),
        sa.Column("season", sa.Integer(), nullable=False),
    )

    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("logo_url", sa.String(255), nullable=True),
        sa.Column("league_id", sa.Integer(), sa.ForeignKey("leagues.id", ondelete="CASCADE"), nullable=False),
    )

    op.create_table(
        "favorite_teams",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "favorite_leagues",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("league_id", sa.Integer(), sa.ForeignKey("leagues.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "fixtures",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("league_id", sa.Integer(), sa.ForeignKey("leagues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("home_team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("away_team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kickoff_utc", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("status", fixture_status, nullable=False, server_default="SCHEDULED"),
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fixture_id", sa.Integer(), sa.ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", notification_kind, nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "fixture_id", "kind", name="uq_user_fixture_kind"),
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("fixtures")
    op.drop_table("favorite_leagues")
    op.drop_table("favorite_teams")
    op.drop_table("teams")
    op.drop_table("leagues")
    op.drop_table("users")
    sa.Enum(name="notificationkind").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="fixturestatus").drop(op.get_bind(), checkfirst=True)
