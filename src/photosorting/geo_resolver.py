"""Geographic resolution: determine location from GPS coordinates using DuckDB Spatial."""

import logging
from pathlib import Path
from typing import Optional

import duckdb

from .config import Config
from .gps_utils import wgs84_to_gcj02

logger = logging.getLogger(__name__)


class GeoResolver:
    """Resolve GPS coordinates to named locations (city or country)."""

    def __init__(self, config: Config, data_dir: Path):
        self.config = config
        self.data_dir = data_dir
        self.ne_shp = data_dir / config.ne_shapefile
        self.china_gpkg = data_dir / config.china_gpkg
        self._conn: Optional[duckdb.DuckDBPyConnection] = None

    def _get_conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect()
            # Use bundled spatial extension if available, otherwise download
            ext_dir = self.data_dir / "duckdb_extensions"
            if ext_dir.exists():
                self._conn.execute(
                    f"SET extension_directory='{ext_dir.as_posix()}'"
                )
                self._conn.execute("LOAD spatial")
            else:
                self._conn.execute("INSTALL spatial; LOAD spatial;")
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def resolve_batch(self, coords: list[tuple[int, float, float]]) -> dict[int, dict]:
        """Resolve a batch of GPS coordinates to locations.

        Args:
            coords: List of (index, latitude, longitude) tuples.

        Returns:
            Dict mapping index to {name_zh, level, province}.
        """
        if not coords:
            return {}

        conn = self._get_conn()

        # Build temporary coordinates table
        conn.execute("DROP TABLE IF EXISTS _temp_coords")
        conn.execute("""
            CREATE TEMP TABLE _temp_coords (idx INTEGER, lat DOUBLE, lon DOUBLE)
        """)
        conn.executemany("INSERT INTO _temp_coords VALUES (?, ?, ?)", coords)

        # Note: coordinate conversion (WGS-84 ↔ GCJ-02) is done before calling
        # resolve_batch via convert_coords_for_china(), based on config.china_crs.
        # The coords passed here are already in the target CRS.

        # Query: first try China cities (ADM level 2), fallback to countries
        query = f"""
            SELECT
                tc.idx,
                COALESCE(
                    CASE
                        WHEN cc.city IS NOT NULL AND cc.province != cc.city
                            THEN cc.province || '-' || cc.city
                        WHEN cc.city IS NOT NULL
                            THEN cc.city
                    END,
                    cn.country, 'Other'
                ) AS location,
                CASE
                    WHEN cc.city IS NOT NULL THEN 'city'
                    WHEN cn.country IS NOT NULL THEN 'country'
                    ELSE 'other'
                END AS level,
                cc.province
            FROM _temp_coords tc
            LEFT JOIN (
                SELECT
                    t.idx,
                    COALESCE(NULLIF(TRIM(string_split(g.NL_NAME_2, '|')[1]), 'NA'), g.NAME_2) AS city,
                    COALESCE(NULLIF(TRIM(string_split(g.NL_NAME_1, '|')[-1]), 'NA'), g.NAME_1) AS province
                FROM _temp_coords t
                JOIN ST_Read('{self.china_gpkg.as_posix()}', layer='ADM_ADM_2') g
                    ON ST_Contains(g.geom, ST_Point(t.lon, t.lat))
            ) cc ON tc.idx = cc.idx
            LEFT JOIN (
                SELECT
                    t.idx,
                    n.NAME AS country
                FROM _temp_coords t
                JOIN ST_Read('{self.ne_shp.as_posix()}') n
                    ON ST_Contains(n.geom, ST_Point(t.lon, t.lat))
            ) cn ON tc.idx = cn.idx AND cc.city IS NULL
            ORDER BY tc.idx
        """

        result = conn.execute(query).fetchall()

        # Clean up
        conn.execute("DROP TABLE IF EXISTS _temp_coords")

        # Build result dict
        resolved = {}
        for idx, location, level, province in result:
            resolved[idx] = {
                "name_zh": location,
                "level": level,
                "province": province,
            }

        return resolved

    def convert_coords_for_china(self, lat: float, lon: float) -> tuple[float, float]:
        """Convert WGS-84 to target CRS if needed for China."""
        if self.config.china_crs == "gcj02":
            return wgs84_to_gcj02(lat, lon)
        return lat, lon