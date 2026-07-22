"""add agent_catalog.inbound_auth

How the agent's AgentCore runtime authenticates its callers: 'iam' (SigV4) or
'jwt' (AgentCore validates the caller's Entra token). AgentCore-sourced and
read-only — refreshed from the runtime's authorizerConfiguration on every catalog
sync — because it is a property of the deployment, not a platform preference.
The proxy signs each upstream call according to it.

'iam' is the right default for every existing row: that is what all six runtimes
were deployed with, and it is what AgentCore does when no authorizer is
configured. A server_default is required rather than optional — the column is NOT
NULL and existing rows have no value, so SQLite's ALTER would refuse the add
without one.

Revision ID: c73f21a5e908
Revises: b41c7d9e0a52
Create Date: 2026-07-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c73f21a5e908'
down_revision: Union[str, None] = 'b41c7d9e0a52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('agent_catalog', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('inbound_auth', sa.String(length=16), nullable=False, server_default='iam')
        )


def downgrade() -> None:
    with op.batch_alter_table('agent_catalog', schema=None) as batch_op:
        batch_op.drop_column('inbound_auth')
