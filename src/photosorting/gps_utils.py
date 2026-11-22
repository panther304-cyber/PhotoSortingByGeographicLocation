"""GPS coordinate utilities: WGS-84 ↔ GCJ-02 conversion.

GCJ-02 (国测局坐标系/火星坐标系) is a Chinese national standard
that applies an obfuscation algorithm to WGS-84 coordinates.
The offset is typically 100-700 meters.
"""

import math

# Constants for the GCJ-02 transformation
_PI = math.pi
_A = 6378245.0  # Semi-major axis
_EE = 0.00669342162296594323  # Eccentricity squared


def _is_out_of_china(lat: float, lon: float) -> bool:
    """Check if coordinates are outside China's bounding box."""
    return not (0.8293 <= lat <= 55.8271 and 72.004 <= lon <= 137.8347)


def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * _PI) + 20.0 * math.sin(2.0 * x * _PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * _PI) + 40.0 * math.sin(y / 3.0 * _PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * _PI) + 320.0 * math.sin(y * _PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * _PI) + 20.0 * math.sin(2.0 * x * _PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * _PI) + 40.0 * math.sin(x / 3.0 * _PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * _PI) + 300.0 * math.sin(x / 30.0 * _PI)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lat: float, lon: float) -> tuple[float, float]:
    """Convert WGS-84 to GCJ-02 coordinates."""
    if _is_out_of_china(lat, lon):
        return lat, lon

    dlat = _transform_lat(lon - 105.0, lat - 35.0)
    dlon = _transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * _PI
    magic = math.sin(radlat)
    magic = 1 - _EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrtmagic) * _PI)
    dlon = (dlon * 180.0) / (_A / sqrtmagic * math.cos(radlat) * _PI)
    return lat + dlat, lon + dlon


def gcj02_to_wgs84(lat: float, lon: float) -> tuple[float, float]:
    """Convert GCJ-02 to WGS-84 coordinates (iterative approximation)."""
    if _is_out_of_china(lat, lon):
        return lat, lon

    # Iterative method: WGS84 ≈ GCJ02 - (GCJ02(WGS84) - GCJ02)
    wgs_lat, wgs_lon = lat, lon
    for _ in range(5):
        gcj_lat, gcj_lon = wgs84_to_gcj02(wgs_lat, wgs_lon)
        delta_lat = gcj_lat - lat
        delta_lon = gcj_lon - lon
        if abs(delta_lat) < 1e-7 and abs(delta_lon) < 1e-7:
            break
        wgs_lat -= delta_lat
        wgs_lon -= delta_lon
    return wgs_lat, wgs_lon


def convert_gps_to_decimal(
    gps_values: tuple[float, ...],
    gps_ref: str,
) -> float | None:
    """Convert GPS EXIF DMS tuple to decimal degrees."""
    if not gps_values or len(gps_values) < 3:
        return None
    d, m, s = float(gps_values[0]), float(gps_values[1]), float(gps_values[2])
    decimal = d + m / 60 + s / 3600
    if gps_ref in ("S", "W"):
        decimal = -decimal
    return decimal