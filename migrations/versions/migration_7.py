"""empty message

Revision ID: migration_6
Revises: layers_parameters
Create Date: 2023-07-27 09:24:48.557069

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'migration_6'
down_revision = 'layers_parameters'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('layer_settings', sa.Column('master_datatype_id', sa.String(64), server_default=None))
    op.add_column('layer_settings', sa.Column('var_name', sa.String(64), server_default=None))


def downgrade():
    op.drop_column('layer_settings', 'master_datatype_id')
    op.drop_column('layer_settings', 'var_name')
