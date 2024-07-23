"""

Revision ID: be4r963g2v8q
Revises: ac2b867d2b7c
Create Date: 2024-07-19

"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "1_dest_org"
down_revision = "0_initdb"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('geoserver_resource', sa.Column('dest_org', sa.String(length=64), nullable=True))


def downgrade():
    op.drop_column('geoserver_resource', 'dest_org')