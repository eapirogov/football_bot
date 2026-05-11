"""fixture stats cache

Revision ID: 0002_fixture_stats_cache
Revises: 0001_init
Create Date: 2026-05-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0002_fixture_stats_cache"
down_revision: Union[str, None] = "0001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fixture_stats_cache",
        sa.Column(
            "fixture_id",
            sa.Integer(),
            sa.ForeignKey("fixtures.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("events_json", JSONB, nullable=False),
        sa.Column("stats_json", JSONB, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("fixture_stats_cache")
