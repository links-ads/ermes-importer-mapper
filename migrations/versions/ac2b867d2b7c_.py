from geoalchemy2.types import Geometry

"""

Revision ID: ac2b867d2b7c
Revises: 
Create Date: 2021-06-07 16:14:42.164738

"""
from alembic import op
import sqlalchemy as sa
import importer


# revision identifiers, used by Alembic.
revision = 'ac2b867d2b7c'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('geoserver_resource',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('datatype_id', sa.String(length=64), nullable=False),
    sa.Column('workspace_name', sa.String(length=64), nullable=False),
    sa.Column('store_name', sa.String(length=64), nullable=False),
    sa.Column('layer_name', sa.String(length=128), nullable=False),
    sa.Column('storage_location', sa.String(length=256), nullable=True),
    sa.Column('created_at', importer.database.TimezoneDateTime(), nullable=False),
    sa.Column('deleted_at', importer.database.TimezoneDateTime(), nullable=True),
    sa.Column('expire_on', importer.database.TimezoneDateTime(), nullable=True),
    sa.Column('start', importer.database.TimezoneDateTime(), nullable=False),
    sa.Column('end', importer.database.TimezoneDateTime(), nullable=False),
    sa.Column('resource_id', sa.String(length=128), nullable=False),
    sa.Column('metadata_id', sa.String(length=128), nullable=True),
    sa.Column('request_code', sa.String(length=64), nullable=True),
    sa.Column('bbox', Geometry(geometry_type='MULTIPOLYGON', from_text='ST_GeomFromEWKT', name='geometry'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('geoserver_resource')
    # ### end Alembic commands ###
