"""add agent_catalog.accepts_files

Whether the chat composer offers file attachments for an agent. Platform-owned
and admin-editable, like ui_mode.

Defaults to false, and a server_default is required rather than optional: the
column is NOT NULL and existing rows have no value for it, so SQLite's ALTER
would refuse the add without one. Off-by-default is also the right behaviour —
an agent whose prompt never mentions images gains nothing from a paperclip, and
an attachment it silently ignores reads to the user as a broken feature.

Revision ID: b41c7d9e0a52
Revises: 9dccfd3be79d
Create Date: 2026-07-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b41c7d9e0a52'
down_revision: Union[str, None] = '9dccfd3be79d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('agent_catalog', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('accepts_files', sa.Boolean(), nullable=False, server_default='0')
        )


def downgrade() -> None:
    with op.batch_alter_table('agent_catalog', schema=None) as batch_op:
        batch_op.drop_column('accepts_files')
