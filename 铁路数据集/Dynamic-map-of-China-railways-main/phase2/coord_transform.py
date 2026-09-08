"""
Coordinate conversions for China maps:
- GCJ-02: 高德 / 腾讯 等 Web 服务
- BD-09: 百度地图 API 返回
- WGS84: Leaflet / OSM

BD-09 → GCJ-02 → WGS84 for Baidu geocoding output.
"""

from __future__ import annotations

import math

_PI = math.pi
_A = 6378245.0
_EE = 0.00669342162296594323


def _out_of_china(lng: float, lat: float) -> bool:
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)


def _transform_lat(x: float, y: float) -> float:
    """x = lng - 105, y = lat - 35 (matches common JS coordtransform)."""
    return (
        -100.0
        + 2.0 * x
        + 3.0 * y
        + 0.2 * y * y
        + 0.1 * x * y
        + 0.2 * math.sqrt(abs(x))
        + (
            (20.0 * math.sin(6.0 * x * _PI) + 20.0 * math.sin(2.0 * x * _PI))
            * 2.0
            / 3.0
        )
        + ((20.0 * math.sin(y * _PI) + 40.0 * math.sin(y / 3.0 * _PI)) * 2.0 / 3.0)
        + ((160.0 * math.sin(y / 12.0 * _PI) + 320 * math.sin(y * _PI / 30.0)) * 2.0 / 3.0)
    )


def _transform_lng(x: float, y: float) -> float:
    """x = lng - 105, y = lat - 35."""
    return (
        300.0
        + x
        + 2.0 * y
        + 0.1 * x * x
        + 0.1 * x * y
        + 0.1 * math.sqrt(abs(x))
        + (
            (20.0 * math.sin(6.0 * x * _PI) + 20.0 * math.sin(2.0 * x * _PI))
            * 2.0
            / 3.0
        )
        + ((20.0 * math.sin(x * _PI) + 40.0 * math.sin(x / 3.0 * _PI)) * 2.0 / 3.0)
        + ((150.0 * math.sin(x / 12.0 * _PI) + 300.0 * math.sin(x / 30.0 * _PI)) * 2.0 / 3.0)
    )


def gcj02_to_wgs84(lng: float, lat: float) -> tuple[float, float]:
    if _out_of_china(lng, lat):
        return lng, lat
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * _PI
    magic = 1 - _EE * math.sin(radlat) ** 2
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / (((_A * (1 - _EE)) / (magic * sqrtmagic)) * _PI)
    dlng = (dlng * 180.0) / ((_A / sqrtmagic) * math.cos(radlat) * _PI)
    mglat = lat + dlat
    mglng = lng + dlng
    return lng * 2 - mglng, lat * 2 - mglat


def bd09_to_gcj02(lng: float, lat: float) -> tuple[float, float]:
    """Baidu BD-09 → GCJ-02 (common eviltransform-style implementation)."""
    x = lng - 0.0065
    y = lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * _PI * 3000.0 / 180.0)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * _PI * 3000.0 / 180.0)
    return z * math.cos(theta), z * math.sin(theta)


def bd09_to_wgs84(lng: float, lat: float) -> tuple[float, float]:
    """Baidu geocoding location → WGS84 for OSM tiles."""
    g_lng, g_lat = bd09_to_gcj02(lng, lat)
    return gcj02_to_wgs84(g_lng, g_lat)
