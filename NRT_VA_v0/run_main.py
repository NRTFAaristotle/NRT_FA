"""
run_main.py
Main script for FRP fire analysis and FREM emissions.
"""
from pathlib import Path
import modules.visualization_1 as viz
from modules.user_input import get_user_inputs
from modules.download import download_period, download_frem_period
from modules.processing import prepare_dataframe,select_area,select_area_frem
from modules.geometry import build_alpha_shape,build_hourly_shapes,envelopes
from modules.ros import compute_ros
from modules.visualization_2 import make_gif
from modules.auxiliary import load_auxiliary_data
from modules.visualization_1 import (plot_perimeter_maps,plot_landcover_maps,
    plot_landcover_burned_area_maps,plot_activity_maps,)
from modules.histogram import *
from modules.statistics import *
from modules.emissions import make_frem_gif

# CONFIGURATION AND OUTPUT DIRECTORIES
config = get_user_inputs()
fire_output_dir = Path("output") / config.fire_name
fire_output_dir.mkdir(parents=True, exist_ok=True)

data_dir = Path("data/raw")
user_bounds = (config.lon_min,config.lat_min,config.lon_max,config.lat_max,)

# DOWNLOAD AND PREPARE FRP DATA
df = download_period(config.start,config.end,config.user,config.password,)
print(f"FRP detections downloaded: {len(df)}")
df = prepare_dataframe(df)
df_fire = select_area(df,config.lat_min,config.lat_max,config.lon_min,config.lon_max,)
print(f"Detections in study area: {len(df_fire)}")
print(f"Data shape: {df_fire.shape}")

if df_fire.empty:
    raise ValueError(
        "No FRP detections were found in the selected study area "
        "and time period. Check the dates and geographic bounds.")
# OUTPUT 1
# PERIMETER + ELEVATION + RIVERS + POPULATION + HOURLY GROWTH
if config.output_perimeter:
    print("\nGenerating Output 1: Perimeter maps...")
    shapes_t = envelopes(df_fire, max_length=0.022)
    print(f"{len(shapes_t)} triangulation perimeters.")
    aux = load_auxiliary_data(shapes=shapes_t,user_bounds=user_bounds,output_perimeter=True,
        output_landcover=False,output_landcover_burned=False,output_activity=False,
        data_dir=data_dir,)

    analysis_data, frames = viz.prepare_hourly_frames(df_fire, shapes_t, config.start, config.end)
    output_dir = fire_output_dir / "perimeter"
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_perimeter_maps(df_fire=df_fire,shapes=shapes_t,dem=aux.dem,extent_dem=aux.extent_dem,
        rivers=aux.rivers,places=aux.places,output_dir=str(output_dir),start=config.start,
        end=config.end,fire_name=config.fire_name,logo_ipma="IPMA.jpg",logo_lsa="LSA_SAF.png",
        analysis_data=analysis_data,frames=frames)

# OUTPUT 2
# LAND COVER + PERIMETER
if config.output_landcover:
    print("\nGenerating Output 2: Land cover maps...")
    shapes_t = envelopes(df_fire, max_length=0.022)
    print(f"{len(shapes_t)} triangulation perimeters.")
    aux = load_auxiliary_data(shapes=shapes_t,user_bounds=user_bounds,output_perimeter=False,
        output_landcover=True,output_landcover_burned=False,
        output_activity=False,
        data_dir=data_dir,)
    analysis_data, frames = viz.prepare_hourly_frames(
        df_fire, shapes_t, config.start, config.end)

    output_dir = fire_output_dir / "landcover"
    output_dir.mkdir(parents=True, exist_ok=True)

    plot_landcover_maps(
        df_fire=df_fire,
        shapes=shapes_t,
        lc_plot=aux.lc_plot,
        extent_dem=aux.extent_lc,
        cmap_lc=aux.cmap_lc,
        norm_lc=aux.norm_lc,
        labels=aux.labels,
        output_dir=str(output_dir),
        start=config.start,
        end=config.end,
        fire_name=config.fire_name,
        logo_ipma="IPMA.jpg",
        logo_lsa="LSA_SAF.png",
        analysis_data=analysis_data,
        frames=frames,)

# OUTPUT 3
# LAND COVER + PERIMETER + BURNED AREA
if config.output_landcover_burned:
    print("\nGenerating Output 3: Land cover and burned area maps...")
    shapes_t = envelopes(df_fire, max_length=0.022)
    print(f"{len(shapes_t)} triangulation perimeters.")
    aux = load_auxiliary_data(
        shapes=shapes_t,
        user_bounds=user_bounds,
        output_perimeter=False,
        output_landcover=False,
        output_landcover_burned=True,
        output_activity=False,
        data_dir=data_dir,)
    analysis_data, frames = viz.prepare_hourly_frames(
        df_fire, shapes_t, config.start, config.end)
    output_dir = fire_output_dir / "landcover_burned_area"
    output_dir.mkdir(parents=True, exist_ok=True)

    plot_landcover_burned_area_maps(
        df_fire=df_fire,
        shapes=shapes_t,
        lc_plot=aux.lc_plot,
        extent_dem=aux.extent_lc,
        cmap_lc=aux.cmap_lc,
        norm_lc=aux.norm_lc,
        labels=aux.labels,
        last_burn_crop=aux.last_burn_crop,
        last_burn_extent=aux.last_burn_extent,
        burn_cmap=aux.burn_cmap,
        burn_norm=aux.burn_norm,
        output_dir=str(output_dir),
        start=config.start,
        end=config.end,
        fire_name=config.fire_name,
        logo_ipma="IPMA.jpg",
        logo_lsa="LSA_SAF.png",
        analysis_data=analysis_data,
        frames=frames)

# OUTPUT 4
# ACTIVITY + PERIMETER + ELEVATION + RIVERS + POPULATION
if config.output_activity:
    print("\nGenerating Output 4: Fire activity maps...")
    shapes_t = envelopes(df_fire, max_length=0.022)
    print(f"{len(shapes_t)} triangulation perimeters.")
    aux = load_auxiliary_data(
        shapes=shapes_t,
        user_bounds=user_bounds,
        output_perimeter=False,
        output_landcover=False,
        output_landcover_burned=False,
        output_activity=True,
        data_dir=data_dir,)

    analysis_data, frames = viz.prepare_hourly_frames(
        df_fire, shapes_t, config.start, config.end)

    output_dir = fire_output_dir / "activity"
    output_dir.mkdir(parents=True, exist_ok=True)

    plot_activity_maps(
        df_fire=df_fire,
        shapes=shapes_t,
        dem=aux.dem,
        extent_dem=aux.extent_dem,
        rivers=aux.rivers,
        places=aux.places,
        output_dir=str(output_dir),
        start=config.start,
        end=config.end,
        fire_name=config.fire_name,
        logo_ipma="IPMA.jpg",
        logo_lsa="LSA_SAF.png",
        analysis_data=analysis_data,
        frames=frames)

# OUTPUT 5 - FRP PROPAGATOR GIF
if config.output_frp_propagator:
    print("\nGenerating Output 5: FRP Propagator GIF...")
    shapes_a = build_hourly_shapes(df_fire, alpha=70)
    ros = compute_ros(shapes_a)
    output_dir = fire_output_dir / "frp_propagator"
    output_dir.mkdir(parents=True, exist_ok=True)
    make_gif(df_fire=df_fire,shapes=shapes_a,ros_df=ros,output=str(output_dir / f"{config.fire_name}.gif"),fps=1)
# OUTPUT 6fogo
# FIRE ACTIVITY HISTOGRAMS
if config.output_histograms:
    print("\nGenerating Output 6: Fire activity histograms...")
    output_dir = fire_output_dir / "histograms"
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_all_days_histograms(df_fire=df_fire,output_name=config.fire_name,output_folder=str(output_dir),)
# OUTPUT 7
# STATISTICS
if config.output_statistics:
    print("\nGenerating Output 7: Statistics...")
    output_dir = fire_output_dir / "statistics"
    output_dir.mkdir(parents=True, exist_ok=True)
    run_statistics(df_fire,output_name=config.fire_name,output_folder=str(output_dir))

# OUTPUT 8
# FREM EMISSIONS GIF
if config.output_emissions:
    print("\nGenerating Output 8: FREM emissions GIF...")
    frem = download_frem_period(start=config.start,end=config.end,user=config.user,password=config.password)
    frem_area = select_area_frem(frem,config.lat_min,config.lat_max,
        config.lon_min,config.lon_max)
    pollutant = input("Choose a pollutant (CO, CO2, CH4, N2O, TPM, PM25): ").upper().strip()
    valid_pollutants = {"CO", "CO2", "CH4", "N2O", "TPM", "PM25"}
    if pollutant not in valid_pollutants:
        raise ValueError(
            f"Invalid pollutant '{pollutant}'. "
            f"Choose one of: {', '.join(sorted(valid_pollutants))}.")
    output_dir = fire_output_dir / "emissions"
    output_dir.mkdir(parents=True, exist_ok=True)
    make_frem_gif(frem_area=frem_area,pollutant=pollutant,
        output=str(output_dir / f"FREM_{config.fire_name}_{pollutant}.gif"),fps=1)
# OPTIONAL CACHE CLEANUP
answer = input("Clean cache? (y/n): ").strip().lower()
if answer == "y":
    import shutil
    n = 0
    for folder in ("frp","frem","burned_area_aoi","corine2018","geonames_aoi","hydrorivers_aoi","dem"):
        folder_path = data_dir / folder
        if folder_path.exists():
            for item in folder_path.iterdir():
                if item.is_file():
                    item.unlink()
                    n += 1
                elif item.is_dir():
                    n += sum(1 for f in item.rglob("*") if f.is_file())
                    shutil.rmtree(item)
    print("==============================")
    print(f"{n} removed files.")
    print("Cache clean.")
    print("==============================")
else:
    print("Cache kept.")