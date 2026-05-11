"""add standings_cache table

Revision ID: 0005_standings_cache
Revises: 0004_user_timezone
Create Date: 2026-05-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005_standings_cache"
down_revision = "0004_user_timezone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "standings_cache",
        sa.Column("league_id", sa.Integer, sa.ForeignKey("leagues.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("season", sa.Integer, primary_key=True),
        sa.Column("data_json", JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("standings_cache")
