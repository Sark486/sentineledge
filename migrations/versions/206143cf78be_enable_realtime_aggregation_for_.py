"""enable realtime aggregation for continuous aggregates

Revision ID: 206143cf78be
Revises: 98e6c996836c
Create Date: 2026-07-15 18:12:30.638356

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '206143cf78be'
down_revision: Union[str, Sequence[str], None] = '98e6c996836c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Continuous aggregates lag at the right edge by their refresh
    # end_offset (5m/1h). Real-time aggregation fills that gap with fresh
    # raw rows so a chart ending at "now" doesn't miss the last bucket(s).
    op.execute("ALTER MATERIALIZED VIEW climate_5m SET (timescaledb.materialized_only = false);")
    op.execute("ALTER MATERIALIZED VIEW climate_1h SET (timescaledb.materialized_only = false);")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER MATERIALIZED VIEW climate_1h SET (timescaledb.materialized_only = true);")
    op.execute("ALTER MATERIALIZED VIEW climate_5m SET (timescaledb.materialized_only = true);")
