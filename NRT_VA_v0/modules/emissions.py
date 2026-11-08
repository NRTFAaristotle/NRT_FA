# emissions.py

import numpy as np
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
from pathlib import Path
import matplotlib.colors as mcolors
from cartopy.io.img_tiles import OSM
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from PIL import Image

#OPEN STREET MAP
tiler = OSM()

POLLUTANTS = {
    "CO": "GCO",
    "CO2": "GCO2",
    "CH4": "GCH4",
    "N2O": "GN2O",
    "TPM": "GTPM",
    "PM25": "GPM25"}

base = plt.cm.hot_r
new_colors = base(np.linspace(0.35, 1.0, 256))
custom_cmap = mcolors.LinearSegmentedColormap.from_list("hot_r_custom",new_colors)

def get_pollutant_variable(pollutant):
    return POLLUTANTS[pollutant]
def get_frem_extent(frem_area, pollutant):
    variable = get_pollutant_variable(pollutant)
    total_emissions = frem_area[variable].sum(dim="time", skipna=True)
    values = total_emissions.values
    active_indices = np.where(np.isfinite(values) & (values > 0))
    if len(active_indices[0]) == 0:
        lon_min = float(frem_area.lon.min())
        lon_max = float(frem_area.lon.max())
        lat_min = float(frem_area.lat.min())
        lat_max = float(frem_area.lat.max())
        return [lon_min, lon_max, lat_min, lat_max]
    lat_active = frem_area.lat.values[active_indices[0]]
    lon_active = frem_area.lon.values[active_indices[1]]
    lat_center = (lat_active.min() + lat_active.max()) / 2
    lon_center = (lon_active.min() + lon_active.max()) / 2
    lat_span = lat_active.max() - lat_active.min()
    lon_span = lon_active.max() - lon_active.min()
    cos_lat = np.cos(np.deg2rad(lat_center))
    lon_span_corrected = lon_span * cos_lat
    half_span = max(lat_span / 2, lon_span_corrected / 2)
    half_span = max(half_span, 0.25) * 1.25
    lon_half = half_span / cos_lat
    lat_half = half_span
    return lon_center - lon_half,lon_center + lon_half,lat_center - lat_half,lat_center + lat_half

def calculate_emission_timeseries(frem_area, pollutant):
    variable = get_pollutant_variable(pollutant)
    hourly_emissions = (frem_area[variable].sum(dim=("lat", "lon")))
    print(hourly_emissions)
    hourly_fre = (frem_area["GFRE"].sum(dim=("lat", "lon")))
    accumulated_emissions = (hourly_emissions.cumsum(dim="time"))
    accumulated_fre = (hourly_fre.cumsum(dim="time"))
    return (hourly_emissions,hourly_fre,accumulated_emissions,accumulated_fre)

def calculate_emission_p90(frem_area, pollutant):
    variable = get_pollutant_variable(pollutant)
    emissions_all = (frem_area[variable] / 1000)
    # Retirar zeros
    positive_emissions = emissions_all.where(emissions_all > 0)
    emission_p90 = float(positive_emissions.quantile(0.90,skipna=True).values)
    return emission_p90

def plot_frem_frame(frem_area,pollutant,hourly_emissions,accumulated_emissions,
    accumulated_fre,frame,map_start,emission_p90,map_extent):
    variable = get_pollutant_variable(pollutant)
    if frame == 0:
        emission_map = (frem_area[variable].isel(time=0) / 1000)
    else:
        emission_map = (frem_area[variable].isel(time=slice(map_start,frame + 1)).sum(dim="time")/ 1000)

    emission_map = emission_map.where(emission_map > 0)
    current_time = (frem_area.time.values[frame])
    p100 = float(emission_map.max(skipna=True).values)

    fig = plt.figure(figsize=(14, 6))
    ax_map = fig.add_subplot(1,2,1,projection=ccrs.PlateCarree())
    ax_map.set_extent(map_extent, crs=ccrs.PlateCarree())
    gl = ax_map.gridlines(draw_labels=True,linewidth=0)
    gl.top_labels = False
    gl.right_labels = False

    im = ax_map.pcolormesh(
        frem_area.lon,
        frem_area.lat,
        emission_map,
        cmap=custom_cmap,
        vmin=0,
        vmax=emission_p90,
        alpha=0.6,
        transform=ccrs.PlateCarree())

    ax_map.text(0.03,0.97,f"P100 (3 h): {p100:.0f} × 10³ kg",
        transform=ax_map.transAxes,
        ha="left",
        va="top",
        fontsize=11,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.35",facecolor="white",edgecolor="black",alpha=0.9),
        zorder=30)
    
    ax_map.coastlines()
    ax_map.add_image(tiler, 12)
    if frame == 0:
        ax_map.set_title(f"{pollutant} emissions\n" f"{str(current_time)[:16]}")
    else:
        start_time = (frem_area.time.values[map_start])
        ax_map.set_title(
            f"{pollutant} emissions\n"
            f"{str(start_time)[:16]} - "
            f"{str(current_time)[:16]}")
    cbar = fig.colorbar(im,ax=ax_map,orientation="vertical",pad=0.02)
    cbar.solids.set_alpha(1)
    cbar.set_label("Emissions ($10^3$ kg)")

    ax_ts = fig.add_subplot(1,2,2)
    times = (frem_area.time.values[:frame + 1])
    emissions = (accumulated_emissions.values[:frame + 1])
    fre = (accumulated_fre.values[:frame + 1])
    line1 = ax_ts.plot(times,emissions,label=f"Accumulated {pollutant} emissions")
    ax_ts.set_xlabel("Time")
    ax_ts.set_ylabel("Accumulated emissions (kg)")
    ax_ts.tick_params(axis="x",rotation=45)
    
    ax_fre = ax_ts.twinx()
    line2 = ax_fre.plot(times,fre,linestyle="--",label="Accumulated FRE")
    ax_fre.set_ylabel("Accumulated FRE (MJ)")
    
    ax_ts.set_title("Accumulated emissions and FRE")
    lines = line1 + line2
    labels = [line.get_label()for line in lines]
    ax_ts.legend(lines,labels,loc="upper left")

    fig.tight_layout()
    # LOGOS
    logo_ipma = Image.open("IPMA.jpg")
    logo_lsasaf = Image.open("LSA_SAF.png")
    img_ipma = OffsetImage(logo_ipma, zoom=0.2)
    img_lsasaf = OffsetImage(logo_lsasaf, zoom=0.10)
    ab1 = AnnotationBbox(img_ipma,(0.15, 0.08),xycoords="figure fraction",frameon=False)
    
    ab2 = AnnotationBbox(img_lsasaf,(0.34, 0.08),xycoords="figure fraction",frameon=False)
    
    fig.add_artist(ab1)
    fig.add_artist(ab2)
    fig.canvas.draw()
    image = np.asarray(fig.canvas.buffer_rgba())[:, :, :3]
    plt.close(fig)
    return image

def make_frem_gif(frem_area,pollutant,output="FREM_emissions.gif",fps=1):

    hourly_emissions, hourly_fre, accumulated_emissions, accumulated_fre = (
        calculate_emission_timeseries(frem_area,pollutant))
    
    emission_p90 = calculate_emission_p90(frem_area,pollutant)
    print(f"P90 das emissões > 0: "f"{emission_p90:.2f} × 10³ kg")
    map_extent = get_frem_extent(frem_area, pollutant)
    frames = []
    frame = plot_frem_frame(frem_area=frem_area,pollutant=pollutant,
        hourly_emissions=hourly_emissions,accumulated_emissions=accumulated_emissions,
        accumulated_fre=accumulated_fre,frame=0,map_start=0,
        emission_p90=emission_p90, map_extent=map_extent)
    frames.append(frame)

    # restantes frames
    for map_start in range(0,frem_area.sizes["time"],3):
        frame_end = map_start + 2

        if frame_end >= frem_area.sizes["time"]:
            frame_end = (frem_area.sizes["time"] - 1)
        if map_start == 0:
            frame = plot_frem_frame(frem_area=frem_area,pollutant=pollutant,
                hourly_emissions=hourly_emissions,accumulated_emissions=accumulated_emissions,
                accumulated_fre=accumulated_fre,frame=frame_end,map_start=map_start,
                emission_p90=emission_p90, map_extent=map_extent)
            frames.append(frame)
        else:
            frame = plot_frem_frame(frem_area=frem_area,pollutant=pollutant,
                hourly_emissions=hourly_emissions,accumulated_emissions=accumulated_emissions,
                accumulated_fre=accumulated_fre,frame=frame_end,map_start=map_start,
                emission_p90=emission_p90,map_extent=map_extent)
            frames.append(frame)
    output = Path(output)
    if not output.is_absolute() and output.parent == Path("."):
        output = Path("output/gifs") / output
    output.parent.mkdir(parents=True, exist_ok=True)
    images = [Image.fromarray(frame) for frame in frames]
    images[0].save(output,save_all=True,append_images=images[1:],duration=1000,loop=0)

    print(f"GIF FREM criado: {output}")
