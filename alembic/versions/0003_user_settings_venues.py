"""user_settings and venues

Revision ID: 0003_user_settings_venues
Revises: 0002_fixture_stats_cache
Create Date: 2026-05-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_user_settings_venues"
down_revision: Union[str, None] = "0002_fixture_stats_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "venues",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("city", sa.String(128), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=True),
    )

    op.add_column("fixtures", sa.Column("venue_id", sa.Integer(), sa.ForeignKey("venues.id", ondelete="SET NULL"), nullable=True))

    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("notifications_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("pre_match_minutes", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("user_settings")
    op.drop_column("fixtures", "venue_id")
    op.drop_table("venues")
