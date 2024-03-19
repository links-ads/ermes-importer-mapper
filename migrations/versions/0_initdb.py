from geoalchemy2.types import Geometry

"""

Revision ID: ac2b867d2b7c
Revises: 
Create Date: 2021-06-07 16:14:42.164738

"""
import sqlalchemy as sa
from alembic import op

import importer

# revision identifiers, used by Alembic.
revision = "0_initdb"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "geoserver_resource",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("datatype_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_name", sa.String(length=64), nullable=False),
        sa.Column("store_name", sa.String(length=64), nullable=False),
        sa.Column("layer_name", sa.String(length=128), nullable=False),
        sa.Column("storage_location", sa.String(length=256), nullable=True),
        sa.Column("created_at", importer.database.TimezoneDateTime(), nullable=False),
        sa.Column("deleted_at", importer.database.TimezoneDateTime(), nullable=True),
        sa.Column("expire_on", importer.database.TimezoneDateTime(), nullable=True),
        sa.Column("start", importer.database.TimezoneDateTime(), nullable=False),
        sa.Column("end", importer.database.TimezoneDateTime(), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=False),
        sa.Column("metadata_id", sa.String(length=128), nullable=True),
        sa.Column("request_code", sa.String(length=64), nullable=True),
        sa.Column("mosaic", sa.Boolean(), server_default="0"),
        sa.Column("timestamps", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "bbox",
            Geometry(geometry_type="MULTIPOLYGON", from_text="ST_GeomFromEWKT", name="geometry"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "layer_settings",
        sa.Column("master_datatype_id", sa.String(64), server_default=None),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("datatype_id", sa.String(length=64), nullable=False),
        sa.Column("style", sa.String(length=64), nullable=True),
        sa.Column("delete_after_days", sa.Integer(), nullable=True),
        sa.Column("delete_after_count", sa.Integer(), nullable=True),
        sa.Column("format", sa.String(length=64), nullable=False),
        sa.Column("time_dimension", sa.Boolean(), server_default="0"),
        sa.Column("time_attribute", sa.String(length=64), server_default=None, nullable=True),
        sa.Column("parameters", sa.String(255), server_default=None),
        sa.Column("var_name", sa.String(64), server_default=None),
        # ### end Alembic commands ###
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("geoserver_resource")
    op.drop_table("layer_settings")
    # ### end Alembic commands ###
