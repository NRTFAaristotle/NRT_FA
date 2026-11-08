"""
geometry.py
Construction of Fire Perimeters.
Methods:
- Alpha Shape with Convex Hull as an alternative;
- Hourly perimeters with cumulative FRP history;
- Envelopes using Delaunay triangulation.
"""
import numpy as np
import pandas as pd
import alphashape
from scipy.spatial import Delaunay, QhullError
from shapely.geometry import MultiPoint, Polygon, LineString
from shapely.ops import unary_union

def build_alpha_shape(df, alpha=70):
    if len(df) == 0:
        return None
    points = np.column_stack((df["LONGITUDE"],df["LATITUDE"]))
    #Few points: uses Convex Hull
    if len(points) < 5:
        return MultiPoint(points).convex_hull
    try:
        shape = alphashape.alphashape(points, alpha)
        if shape is None or shape.is_empty:
            return MultiPoint(points).convex_hull
        return shape
    except Exception:
        return MultiPoint(points).convex_hull

def build_hourly_shapes(df, alpha=70):
    df = df.sort_values("ACQTIME").copy()
    all_hours = pd.date_range(start=df["HOUR"].min(),end=df["HOUR"].max(),freq="1h")
    pixel_dict = {}
    shapes = []
    for hour in all_hours:
        hour_df = df[df["HOUR"] == hour]
        for row in hour_df.itertuples():
            key = (row.LATITUDE, row.LONGITUDE)
            if key not in pixel_dict:
                pixel_dict[key] = row.FRP
            else:
                pixel_dict[key] = max(pixel_dict[key],row.FRP)
        if len(pixel_dict) == 0:
            shapes.append({"HOUR": hour,"SHAPE": None,"NPIX": 0,"TOTAL_FRP": 0})
            continue
        df_map = pd.DataFrame([(lat, lon, frp)
                for (lat, lon), frp in pixel_dict.items()],
            columns=["LATITUDE", "LONGITUDE", "FRP"])
        shape = build_alpha_shape(df_map, alpha)
        shapes.append({"HOUR": hour,"SHAPE": shape,"NPIX": len(df_map),"TOTAL_FRP": df_map["FRP"].sum()})
    return shapes

def envelopes(df, max_length=0.022):
    df["TIME_HOUR"] = df["ACQTIME"].dt.floor("1h")
    times_hourly = np.sort(df["TIME_HOUR"].unique())
    shapes = {}
    smooth = 0.003
    for t in times_hourly:
        shape_pixels = df[df["TIME_HOUR"] <= t].copy()
        shape_pixels = shape_pixels.drop_duplicates(subset=["LATITUDE", "LONGITUDE"])
        print(t)
        print("Unique pixels:", len(shape_pixels))
        coords = np.column_stack((shape_pixels["LONGITUDE"],shape_pixels["LATITUDE"]))
        if len(coords) == 1:
            continue
        elif len(coords) == 2:
            fire_shape = LineString(coords)
            shapes[pd.Timestamp(t)] = fire_shape
            print(">>> Shape stored")
            continue
        elif len(coords) < 3:
            continue
        try:
            tri = Delaunay(coords)
        except QhullError:
            continue
        triangles = []
        for simplex in tri.simplices:
            pts = coords[simplex]
            d1 = np.linalg.norm(pts[0] - pts[1])
            d2 = np.linalg.norm(pts[1] - pts[2])
            d3 = np.linalg.norm(pts[2] - pts[0])
            max_side = max(d1, d2, d3)
            if max_side <= max_length:
                triangles.append(Polygon(pts))
        if len(triangles) == 0:
            continue
        fire_shape = unary_union(triangles)
        fire_shape = (fire_shape.buffer(smooth).buffer(-smooth))
        shapes[pd.Timestamp(t)] = fire_shape
    print("Shapes stored:", len(shapes))
    use_perimeters = len(shapes) > 0
    if use_perimeters:
        print("First shape:", min(shapes.keys()))
        print("Last shape :", max(shapes.keys()))
    else:
        print("No fire perimeter could be generated.")
        print("GIFs will be created using MTG detections only.")
    return shapes