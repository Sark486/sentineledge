"""drop devices.is_online

`is_online` was only ever written (and only ever set to true) — nothing read it
back, no sweeper reset it, and both the API and the dashboard derive liveness
from `last_seen` against the online window instead.

Revision ID: 4c1f0a7b92d5
Revises: 206143cf78be
Create Date: 2026-08-01 11:20:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4c1f0a7b92d5'
down_revision: Union[str, Sequence[str], None] = '206143cf78be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('devices', 'is_online')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        'devices',
        sa.Column('is_online', sa.Boolean(), nullable=True),
    )
