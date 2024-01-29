"""empty message

Revision ID: layers_parameters
Revises: 2a5v589er94d
Create Date: 2023-07-27 09:24:48.557069

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'layers_parameters'
down_revision = '2a5v589er94d'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('layer_settings', sa.Column('parameters', sa.String(255), server_default=None))


def downgrade():
    op.drop_column('layer_settings', 'parameters')
