"""add kickoff to notificationkind enum

Revision ID: 0006_notification_kickoff
Revises: 0005_standings_cache
Create Date: 2026-05-12

"""
from alembic import op

revision = "0006_notification_kickoff"
down_revision = "0005_standings_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE notificationkind ADD VALUE IF NOT EXISTS 'kickoff'")


def downgrade() -> None:
    # PostgreSQL не поддерживает удаление значений из enum без пересоздания типа
    pass
