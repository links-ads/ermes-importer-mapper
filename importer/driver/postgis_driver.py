import logging
from typing import List

import geopandas as gpd
from pandas.io import sql
from settings.instance import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

LOG = logging.getLogger(__name__)


class PostGISDriver:
    def __init__(self):
        self.engine = create_engine(settings.database_url())
        session_factory = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.SessionLocal = scoped_session(session_factory)

    def save_table(self, gpd_df: gpd.GeoDataFrame, table_name: str):
        gpd_df.to_postgis(table_name, self.engine, index=True, index_label="Index")

    def get_table(self, table_name: str, geom_col: str = "geometry"):
        sql_script = f'SELECT * FROM "{table_name}"'
        try:
            return gpd.GeoDataFrame.from_postgis(sql_script, self.engine, geom_col=geom_col)
        except Exception:
            return gpd.GeoDataFrame.from_postgis(sql_script, self.engine, geom_col="geom")

    def get_table_value(
        self,
        table_names: List[str],
        column: str,
        point: str,
        geom_col: str = "geometry",
        date_start_col: str = "date_start",
        date_end_col: str = "date_end",
        creation_date_col: str = "computation_time",
    ):
        sql_script = f"""
        WITH summary AS (
            SELECT {column},
                {date_start_col},
                {date_end_col},
                {geom_col},
                row_number() over (partition by {date_start_col} order by {creation_date_col} DESC) as rank
            FROM (
        """
        for table_name in table_names[:-1]:
            sql_script += f'SELECT {column},{geom_col},{date_start_col},{date_end_col},{creation_date_col}\
                FROM "{table_name}" UNION ALL '
        sql_script += (
            f'SELECT {column},{geom_col},{date_start_col},{date_end_col},{creation_date_col} FROM "{table_names[-1]}"'
        )
        sql_script += f"""
            ) as all_tabs
            WHERE ST_Intersects({geom_col}, 'SRID=4326;POINT({point})')
        )
        select {column},
               {date_start_col},
               {date_end_col},
               {geom_col}
        from summary
        where rank = 1
        order by {date_start_col};
        """
        return gpd.GeoDataFrame.from_postgis(sql_script, self.engine, geom_col=geom_col)

    def drop_table(self, table_name: str):
        sql_script = f'DROP TABLE IF EXISTS "{table_name}"'
        try:
            sql.execute(sql_script, self.engine)
        except Exception as e:
            LOG.warning(e)

    def execute(self, sql_script: str):
        sql.execute(sql_script, self.engine)
