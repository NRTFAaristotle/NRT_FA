"""
ros.py
"""
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

def _extract_points(geom):
    if geom is None:
        return []
    pts = []
    if geom.geom_type == "Polygon":
        pts.extend(list(geom.exterior.coords))
    elif geom.geom_type == "MultiPolygon":
        for poly in geom.geoms:
            pts.extend(list(poly.exterior.coords))
    elif geom.geom_type == "LineString":
        pts.extend(list(geom.coords))
    elif geom.geom_type == "MultiLineString":
        for line in geom.geoms:
            pts.extend(list(line.coords))
    elif geom.geom_type == "Point":
        pts.append((geom.x, geom.y))
    elif geom.geom_type == "MultiPoint":
        pts.extend([(p.x, p.y) for p in geom.geoms])
    return pts

def extract_ros_points(prev_shape, curr_shape):

    if prev_shape is None or curr_shape is None:
        return None, None, 0.0
    g = gpd.GeoSeries([prev_shape, curr_shape],crs="EPSG:4326").to_crs("EPSG:3035")
    prev = g.iloc[0]
    curr = g.iloc[1]
    curr_vertices = _extract_points(curr)
    if len(curr_vertices) == 0:
        return None, None, 0.0
    max_distance = 0.0
    best_curr = None
    best_prev = None
    for x, y in curr_vertices:
        p = Point(x, y)
        d = p.distance(prev)
        if d > max_distance:
            max_distance = d
            best_curr = p
            try:
                if prev.boundary.is_empty:
                    best_prev = prev
                else:
                    best_prev = prev.boundary.interpolate(prev.boundary.project(p))
            except Exception:
                best_prev = prev.centroid
    return best_curr, best_prev, max_distance

def compute_ros(shapes):
    results = []
    for i in range(1, len(shapes)):
        prev = shapes[i - 1]
        curr = shapes[i]
        curr_point, prev_point, dist = extract_ros_points( prev["SHAPE"],curr["SHAPE"])
        dt = (curr["HOUR"] -prev["HOUR"]).total_seconds() / 3600
        if dt <= 0:
            ros = 0.0
        else:
            ros = dist / dt
        results.append(
            {"HOUR": curr["HOUR"],"ROS_MAX_m_h": ros,"DISTANCE_m": dist,"CURR_POINT": curr_point,"PREV_POINT": prev_point})
    ros_df = pd.DataFrame(results)
    ros_df = ros_df.sort_values("HOUR").reset_index(drop=True)
    return ros_df