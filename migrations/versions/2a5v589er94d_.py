"""empty message

Revision ID: 2a5v589er94d
Revises: 3a5c328de87f
Create Date: 2023-07-26 09:24:48.557069

"""
from alembic import op
import sqlalchemy as sa
import importer


# revision identifiers, used by Alembic.
revision = '2a5v589er94d'
down_revision = '3a5c328de87f'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('layer_settings', sa.Column('time_dimension', sa.Boolean(), server_default="0"))
    op.add_column('layer_settings', sa.Column('time_attribute', sa.String(length=64), server_default=None, nullable=True))


def downgrade():
    op.drop_column('layer_settings', 'time_dimension')
    op.drop_column('layer_settings', 'time_attribute')