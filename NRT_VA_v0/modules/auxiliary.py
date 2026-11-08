"""
Auxiliary data loading and preparation for FRP Fire Analysis.

"""

from pathlib import Path
from types import SimpleNamespace
import re
import h5py
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
from matplotlib.colors import ListedColormap, BoundaryNorm
from rasterio.windows import from_bounds
from modules.download_auxiliary import CLC,download_corine2018,download_dem_aoi,download_hydrorivers,download_geonames,download_burned_area_aoi

def load_dem(path, xmin, xmax, ymin, ymax):
    src_dem = rasterio.open(path)
    window_dem = from_bounds( xmin, ymin, xmax, ymax, src_dem.transform)
    dem = src_dem.read(1, window=window_dem)
    transform_dem = src_dem.window_transform(window_dem)
    left_dem = transform_dem.c
    right_dem = left_dem + dem.shape[1] * transform_dem.a
    top_dem = transform_dem.f
    bottom_dem = top_dem + dem.shape[0] * transform_dem.e
    extent_dem = [left_dem, right_dem,bottom_dem, top_dem,]
    src_dem.close()
    return dem, extent_dem

def load_rivers(path, xmin, xmax, ymin, ymax):
    rios = gpd.read_file(path, layer="HydroRIVERS_v10_eu")
    rios = rios.cx[xmin:xmax, ymin:ymax]
    return rios

def load_populated_places(path,xmin,xmax,ymin,ymax,max_places=25,min_distance_fraction=0.06,):
    cols = ["geonameid","name","asciiname","alternatenames","latitude","longitude",
        "feature_class","feature_code","country_code","cc2","admin1","admin2",
        "admin3","admin4","population","elevation","dem","timezone","modification_date",]
    places = pd.read_csv( path,sep="\t",names=cols,low_memory=False,)
    places = places[(places["latitude"] >= ymin) & (places["latitude"] <= ymax) & (places["longitude"] >= xmin)
        & (places["longitude"] <= xmax)].copy()
    places = places[places["feature_class"] == "P"].copy()
    places_all = places.copy()
    places = places[
        places["feature_code"].isin(["PPLC","PPLA","PPLA2","PPLA3","PPLA4","PPL",]) ].copy()
    places = places[places["population"] > 0].copy()
    if len(places) == 0:
        places = places_all[places_all["feature_code"] == "PPL"].copy()
    places = places.sort_values("population", ascending=False)
    places = places.drop_duplicates(subset=["name"])
    width = xmax - xmin
    height = ymax - ymin
    diag = np.sqrt(width**2 + height**2)
    min_distance = min_distance_fraction * diag
    selected = []
    for _, row in places.iterrows():
        keep = True
        for p in selected:
            distance = np.sqrt((row["longitude"] - p["longitude"])**2 + (row["latitude"] - p["latitude"])**2)
            if distance < min_distance:
                keep = False
                break
        if keep:
            selected.append(row)
        if len(selected) == max_places:
            break
    if len(selected) > 0:
        places = pd.DataFrame(selected)
    else:
        places = places.iloc[0:0]
    return places

def load_landcover(path, xmin, xmax, ymin, ymax):
    f = h5py.File(path, "r")
    landcover = f["lccs_class"][0]
    lat_lc = f["lat"][:]
    lon_lc = f["lon"][:]
    f.close()
    dx = lon_lc[1] - lon_lc[0]
    dy = abs(lat_lc[1] - lat_lc[0])
    c0 = max(0, np.searchsorted(lon_lc, xmin - dx / 2))
    c1 = min( len(lon_lc), np.searchsorted(lon_lc, xmax + dx / 2),)
    lat_rev = lat_lc[::-1]
    r0 = max(0, np.searchsorted(lat_rev, ymin - dy / 2))
    r1 = min(len(lat_lc),np.searchsorted(lat_rev, ymax + dy / 2))
    row_start = len(lat_lc) - r1
    row_end = len(lat_lc) - r0
    lc_crop = landcover[row_start:row_end, c0:c1]
    extent_lc = [lon_lc[c0] - dx / 2, lon_lc[c1 - 1] + dx / 2, lat_lc[row_end - 1] - dy / 2,
        lat_lc[row_start] + dy / 2,]
    landcover_info = {
        0: ("No Data", "#000000"),
        10: ("Rainfed Crop", "#FFFF64"),
        11: ("Rainfed Herb.", "#FFFF64"),
        12: ("Rainfed Tree", "#FFFF00"),
        20: ("Irrigated Crop", "#99D9D9"),
        30: ("Crop/Nat. Mosaic", "#DCEF63"),
        40: ("Nat./Crop Mosaic", "#CDCD66"),
        50: ("Evergreen Broadleaf", "#006400"),
        60: ("Deciduous Broadleaf", "#00A000"),
        61: ("Decid. Broad. Closed", "#00A000"),
        62: ("Decid. Broad. Open", "#A8D400"),
        70: ("Evergreen Needleleaf", "#003C00"),
        71: ("Ever. Needle Closed", "#003C00"),
        72: ("Ever. Needle Open", "#005000"),
        80: ("Deciduous Needleleaf", "#286400"),
        81: ("Decid. Needle Closed", "#286400"),
        82: ("Decid. Needle Open", "#3C7800"),
        90: ("Mixed Forest", "#788200"),
        100: ("Tree/Shrub Mosaic", "#8C9600"),
        110: ("Herbaceous Mosaic", "#C8AA00"),
        120: ("Shrubland", "#AA7800"),
        121: ("Evergreen Shrub", "#966400"),
        122: ("Deciduous Shrub", "#AA7800"),
        130: ("Grassland", "#FFB432"),
        140: ("Lichens & Mosses", "#F0BEB4"),
        150: ("Sparse Vegetation", "#FFD27D"),
        151: ("Sparse Trees", "#FFD27D"),
        152: ("Sparse Shrubs", "#FFE6A0"),
        153: ("Sparse Herbs", "#FFF0B4"),
        160: ("Flooded Forest", "#009578"),
        170: ("Saline Forest", "#00C8AA"),
        180: ("Flooded Shrub/Herb", "#14D28C"),
        190: ("Urban", "#C80000"),
        200: ("Bare Ground", "#F0F0F0"),
        201: ("Bare Ground (Cons.)", "#D2D2D2"),
        202: ("Bare Ground (Loose)", "#FFFFFF"),
        210: ("Water", "#1450C8"),
        220: ("Snow & Ice", "#FFFFFF"),}

    classes_present = np.unique(lc_crop)
    classes_present = classes_present[classes_present != 0]
    classes_present = [ int(c) for c in classes_present if int(c) in landcover_info]

    colors = [landcover_info[c][1] for c in classes_present]
    labels = [landcover_info[c][0] for c in classes_present]

    lc_plot = np.full(lc_crop.shape, np.nan)
    for j, cls in enumerate(classes_present):
        lc_plot[lc_crop == cls] = j
    cmap_lc = ListedColormap(colors)
    norm_lc = BoundaryNorm(np.arange(len(colors) + 1) - 0.5,cmap_lc.N,)
    return lc_plot, extent_lc, cmap_lc, norm_lc, labels

def load_burned_area(raster_paths):
    if isinstance(raster_paths, (str, Path)):
        raster_paths = [raster_paths]
    paths = [Path(path) for path in raster_paths]
    if not paths:
        raise ValueError("No Burnt Area rasters provided.")
    def get_year_month(path):
        match = re.search( r"burned_area_(\d{4})(\d{2})_", path.name)
        if not match:
            raise ValueError(f"Unexpected Burnt Area filename: {path.name}")
        return int(match.group(1)), int(match.group(2))
    paths.sort(key=get_year_month)
    with rasterio.open(paths[0]) as src:
        shape = src.shape
        crs = src.crs
        transform = src.transform
        bounds = src.bounds
        extent = [bounds.left,bounds.right,bounds.bottom,bounds.top]
        last_burn = np.full(shape, np.nan, dtype=np.float32)
    for path in paths:
        year, month = get_year_month(path)
        with rasterio.open(path) as src:
            if (
                src.shape != shape
                or src.crs != crs
                or src.transform != transform):
                raise ValueError(f"Incompatible Burnt Area raster grid: {path.name}")

            data = src.read(1, masked=True)
            values = data.filled(0)
            detected = ((~np.ma.getmaskarray(data)) & (values >= 1) & (values <= 366))
            last_burn[detected] = year
    burn_colors = ["#cccccc","#999999","#666666","#333333","#000000",]
    burn_cmap = ListedColormap(burn_colors)
    burn_norm = BoundaryNorm([2020.5, 2021.5, 2022.5, 2023.5, 2024.5, 2025.5], burn_cmap.N)
    return last_burn, extent, burn_cmap, burn_norm

def _load_corine_for_plot(bounds, data_dir):
    with requests.Session() as session:
        layer = download_corine2018(bounds,cache_dir=data_dir,session=session)
    if layer is None:
        raise RuntimeError(
            "Could not load CORINE 2018 land cover for the selected study area. "
            "Check the connection and try again.")
    raw_classes = layer.data
    present_classes = sorted(int(value) for value in np.unique(raw_classes[np.isfinite(raw_classes)])
        if int(value) in CLC)
    if not present_classes:
        raise RuntimeError("No valid CORINE 2018 classes were found in the selected area.")
    lc_plot = np.full(raw_classes.shape, np.nan, dtype=float)
    for index, class_code in enumerate(present_classes):
        lc_plot[raw_classes == class_code] = index
    labels = [CLC[class_code][0] for class_code in present_classes]
    colors = [CLC[class_code][1] for class_code in present_classes]
    cmap_lc = ListedColormap(colors)
    norm_lc = BoundaryNorm(np.arange(len(colors) + 1) - 0.5, cmap_lc.N,)
    return lc_plot, list(layer.extent), cmap_lc, norm_lc, labels

def load_auxiliary_data(shapes,user_bounds,output_perimeter=False,output_landcover=False,
    output_landcover_burned=False,output_activity=False,data_dir="data/raw",):

    try:
        lon_min, lat_min, lon_max, lat_max = map(float, user_bounds)
    except (TypeError, ValueError) as exc:
        raise ValueError("user_bounds must be (lon_min, lat_min, lon_max, lat_max).") from exc
    if not (
        -180 <= lon_min < lon_max <= 180
        and -90 <= lat_min < lat_max <= 90):
        raise ValueError("Invalid user-selected geographic bounds.")

    xmin, xmax, ymin, ymax = lon_min, lon_max, lat_min, lat_max
    download_bounds = (lon_min, lat_min, lon_max, lat_max)
    data_dir = Path(data_dir)

    need_dem = output_perimeter or output_activity
    need_rivers = output_perimeter or output_activity
    need_places = output_perimeter or output_activity
    need_landcover = output_landcover or output_landcover_burned
    need_burned_area = output_landcover_burned

    dem = None
    extent_dem = None
    rivers = None
    places = None
    lc_plot = None
    extent_lc = None
    cmap_lc = None
    norm_lc = None
    labels = None
    last_burn_crop = None
    last_burn_extent = None
    burn_cmap = None
    burn_norm = None
    if need_dem:
        dem_path = download_dem_aoi(download_bounds, data_dir)
        dem, extent_dem = load_dem(str(dem_path),xmin,xmax,ymin,ymax,)
    if need_rivers:
        rivers_path = download_hydrorivers(download_bounds,data_dir=data_dir)
        rivers = load_rivers(str(rivers_path),xmin,xmax,ymin,ymax,)
    if need_places:
        places_path = download_geonames(download_bounds,data_dir=data_dir)
        places = load_populated_places(str(places_path), xmin, xmax, ymin, ymax)
    if need_landcover:
        lc_plot,extent_lc,cmap_lc, norm_lc, labels, = _load_corine_for_plot(download_bounds, data_dir)
    if need_burned_area:
        burned_area_paths = download_burned_area_aoi(download_bounds,data_dir=data_dir,)
        last_burn_crop,last_burn_extent,burn_cmap,burn_norm= load_burned_area(burned_area_paths)

    print()
    print("Auxiliary data loaded")
    print("Study/map extent:", (xmin, xmax, ymin, ymax))
    print("DEM:", None if dem is None else dem.shape)
    print("Rivers:", None if rivers is None else len(rivers))
    print("Populated places:", None if places is None else len(places))
    print("Land cover:", None if lc_plot is None else lc_plot.shape)
    print("Burned area:", None if last_burn_crop is None else last_burn_crop.shape)

    return SimpleNamespace(dem=dem,extent_dem=extent_dem,rivers=rivers,places=places,
        lc_plot=lc_plot,extent_lc=extent_lc,cmap_lc=cmap_lc,norm_lc=norm_lc, labels=labels,
        last_burn_crop=last_burn_crop,last_burn_extent=last_burn_extent,burn_cmap=burn_cmap,
        burn_norm=burn_norm,xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax, study_bounds=download_bounds,)
