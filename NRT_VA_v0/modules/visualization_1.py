import imageio.v2 as imageio
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from matplotlib.colorbar import ColorbarBase
from pyproj import Transformer
from shapely.ops import transform
from shapely.geometry import LineString, Polygon, MultiPolygon, GeometryCollection

plt.rcParams.update({"axes.titlesize": 12, "axes.labelsize": 12, "xtick.labelsize": 12, "ytick.labelsize": 12})
def classify_period(hour):
    if 9 <= hour < 19:
        return "Day"
    elif 19 <= hour < 24:
        return "Sunset"
    return "Night"
def get_map_limits(shapes):
    bounds = [shape.bounds for shape in shapes.values()]
    xmin = min(b[0] for b in bounds)
    ymin = min(b[1] for b in bounds)
    xmax = max(b[2] for b in bounds)
    ymax = max(b[3] for b in bounds)
    margin = max(0.10 * max(xmax - xmin, ymax - ymin), 0.03)
    return xmin - margin, xmax + margin, ymin - margin, ymax + margin
def prepare_hourly_frames(df_fire, shapes, start, end):
    analysis_data = df_fire[(df_fire["ACQTIME"] >= start) & (df_fire["ACQTIME"] <= end)].copy()
    analysis_data["TIME_HOUR"] = analysis_data["ACQTIME"].dt.floor("1h")
    times = sorted(shapes.keys()) if len(shapes) > 0 else []
    use_perimeters = len(times) > 0
    last_data_time = analysis_data["ACQTIME"].max()
    days = pd.date_range(start=pd.Timestamp(start).normalize(), end=pd.Timestamp(end).normalize(), freq="D")
    frames = []
    shape_idx = 0
    for day in days:
        if day.normalize() == last_data_time.normalize():
            last_hour = last_data_time.floor("1h")
            frame_times = pd.date_range(start=day, end=last_hour + pd.Timedelta(hours=1), freq="1h")
        else:
            frame_times = pd.date_range(start=day, end=day + pd.Timedelta(hours=24), freq="1h")
        last_shape = None
        for i in range(len(frame_times) - 1):
            t1, t2 = frame_times[i], frame_times[i + 1]
            if use_perimeters:
                while shape_idx < len(times) and times[shape_idx] <= t1:
                    shape_idx += 1
                if shape_idx == 0:
                    shape_old = shape_new = growth = GeometryCollection()
                else:
                    shape_current = shapes[times[shape_idx - 1]]
                    if last_shape is None:
                        shape_old = shape_new = shape_current
                        growth = GeometryCollection()
                    else:
                        shape_old = last_shape
                        shape_new = shape_current
                        growth = shape_new.difference(shape_old)
                    last_shape = shape_new
            else:
                shape_old = shape_new = growth = GeometryCollection()
            history = analysis_data[analysis_data["TIME_HOUR"] <= t2].copy()
            history = history.drop_duplicates(subset=["LATITUDE", "LONGITUDE"])
            frames.append({"T1": t1, "T2": t2, "SHAPE_OLD": shape_old, "SHAPE_NEW": shape_new, "GROWTH": growth, "HISTORY": history})
    return analysis_data, frames
def plot_shape(ax, shape, color="black", linewidth=2, zorder=20):
    if isinstance(shape, LineString):
        x, y = shape.xy
        ax.plot(x, y, color=color, linewidth=linewidth, zorder=zorder)
    elif isinstance(shape, Polygon):
        x, y = shape.exterior.xy
        ax.plot(x, y, color=color, linewidth=linewidth, zorder=zorder)
        for interior in shape.interiors:
            xi, yi = interior.xy
            ax.plot(xi, yi, color=color, linewidth=linewidth, zorder=zorder)
    elif isinstance(shape, MultiPolygon):
        for poly in shape.geoms:
            plot_shape(ax, poly, color=color, linewidth=linewidth, zorder=zorder)
def plot_growth(ax, growth):
    if isinstance(growth, Polygon):
        x, y = growth.exterior.xy
        ax.fill(x, y, color="orange", alpha=0.7)
    elif isinstance(growth, MultiPolygon):
        for poly in growth.geoms:
            plot_growth(ax, poly)
def add_logos(fig, logo_ipma=None, logo_lsa=None, ipma_position=(0.45, 0.045), lsa_position=(0.52, 0.045)):
    for logo, position, zoom in ((logo_ipma, ipma_position, 0.10), (logo_lsa, lsa_position, 0.05)):
        if logo is not None:
            if isinstance(logo, (str, os.PathLike)):
                logo = plt.imread(logo)
            fig.add_artist(AnnotationBbox(OffsetImage(logo, zoom=zoom), position, xycoords="figure fraction", frameon=False))
def _prepare_output_dirs(output_dir):
    os.makedirs(output_dir, exist_ok=True)
    gif_dir = os.path.join(output_dir, "GIFs")
    snapshot_dir = os.path.join(output_dir, "snapshots")
    os.makedirs(gif_dir, exist_ok=True)
    os.makedirs(snapshot_dir, exist_ok=True)
    return gif_dir, snapshot_dir
def create_daily_gif(images, output_file, duration=2000):
    if images:
        imageio.mimsave(output_file, images, duration=duration, loop=0)
def _update_daily_gif(daily_pngs, current_day, frame_day, gif_dir, fire_name):
    if current_day is None:
        return daily_pngs, frame_day
    if frame_day != current_day:
        create_daily_gif(daily_pngs, os.path.join(gif_dir, f"{fire_name}_{current_day:%Y%m%d}.gif"))
        return [], frame_day
    return daily_pngs, current_day
def _finish_daily_gif(daily_pngs, current_day, gif_dir, fire_name):
    if daily_pngs:
        create_daily_gif(daily_pngs, os.path.join(gif_dir, f"{fire_name}_{current_day:%Y%m%d}.gif"))
def _add_footer(fig, run_time):
    if run_time is not None:
        fig.text(0.01, 0.01, f"Generated: {run_time} | Carvalho et al. (2026)", fontsize=10, color="dimgray", ha="left", va="bottom")
def _save_frame(fig, daily_pngs, snapshot_dir, snapshot_name, t1):
    fig.canvas.draw()
    daily_pngs.append(np.asarray(fig.canvas.buffer_rgba()).copy())
    if t1.hour % 6 == 0:
        fig.savefig(os.path.join(snapshot_dir, f"{snapshot_name}{t1:%Y%m%d_%H%M}.png"), dpi=150)
    plt.close(fig)
def _set_map_axes(ax, limits):
    xmin, xmax, ymin, ymax = limits
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("auto")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(alpha=0.25)
def _plot_rivers(ax, rivers):
    try:
        rios_plot = rivers[rivers.geometry.notna() & (~rivers.geometry.is_empty)]
        if not rios_plot.empty:
            rios_plot.plot(ax=ax, color="deepskyblue", linewidth=0.5, alpha=0.8, zorder=2)
    except Exception as e:
        print(f"Skipping rivers: {e}")
def _plot_places(ax, places):
    for _, row in places.iterrows():
        ax.scatter(row["longitude"], row["latitude"], s=45, marker="^", color="royalblue", edgecolor="white", linewidth=0.8, zorder=25)
        ax.text(row["longitude"] + 0.005, row["latitude"] + 0.003, row["name"], fontsize=10, color="black", ha="left", va="center", zorder=26, bbox=dict(facecolor="white", edgecolor="none", alpha=0.65, pad=0.15))
def _add_dem_colorbar(fig, im_dem, position):
    cbar = fig.colorbar(im_dem, cax=fig.add_axes(position))
    cbar.set_label("Elevation (m)")
def _add_landcover_colorbar(fig, cmap_lc, norm_lc, labels, position):
    cb = ColorbarBase(fig.add_axes(position), cmap=cmap_lc, norm=norm_lc, boundaries=np.arange(len(labels) + 1) - 0.5, ticks=np.arange(len(labels)))
    cb.ax.set_yticklabels(labels, fontsize=9)
    cb.ax.tick_params(length=0)
def _prepare_frames(df_fire, shapes, start, end, analysis_data, frames):
    if analysis_data is None or frames is None:
        return prepare_hourly_frames(df_fire, shapes, start, end)
    return analysis_data, frames
# OUTPUT 1: PERIMETER + ALTITUDE + RIVERS + POPULATION + ΔA
def plot_perimeter_maps(df_fire, shapes, dem, extent_dem, rivers, places, output_dir, start, end, fire_name="Wildfire",
    logo_ipma=None, logo_lsa=None, run_time=None, analysis_data=None, frames=None):
    gif_dir, snapshot_dir = _prepare_output_dirs(output_dir)
    daily_pngs = []
    current_day = None
    analysis_data, frames = _prepare_frames(df_fire, shapes, start, end, analysis_data, frames)
    limits = get_map_limits(shapes)
    first_hour = analysis_data["ACQTIME"].dt.floor("1h").min()
    initial_fire = analysis_data[analysis_data["ACQTIME"].dt.floor("1h") == first_hour]
    lat0, lon0 = initial_fire["LATITUDE"].mean(), initial_fire["LONGITUDE"].mean()
    utm_zone = int((lon0 + 180) / 6) + 1
    utm_epsg = (32600 if lat0 >= 0 else 32700) + utm_zone
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)
    print("Creating perimeter maps...")
    print(f"Maps to create: {len(frames)}")
    for i, frame in enumerate(frames, start=1):
        t1, t2 = frame["T1"], frame["T2"]
        daily_pngs, current_day = _update_daily_gif(daily_pngs, current_day, t1.normalize(), gif_dir, fire_name)
        shape_old, shape_new, growth = frame["SHAPE_OLD"], frame["SHAPE_NEW"], frame["GROWTH"]
        shape_old_utm = transform(transformer.transform, shape_old)
        shape_new_utm = transform(transformer.transform, shape_new)
        dA = shape_new_utm.area / 10000.0 - shape_old_utm.area / 10000.0
        fig = plt.figure(figsize=(18, 11))
        add_logos(fig, logo_ipma, logo_lsa)
        ax = fig.add_axes([0.05, 0.12, 0.80, 0.84])
        im_dem = ax.imshow(dem, cmap="Greys", extent=extent_dem)
        ax.set_aspect("auto", adjustable="box")
        _plot_rivers(ax, rivers)
        _plot_places(ax, places)
        plot_shape(ax, shape_old, color="black", linewidth=2, zorder=20)
        history = frame["HISTORY"]
        ax.scatter(history["LONGITUDE"], history["LATITUDE"], color="#FF0033", s=200, alpha=1.0, zorder=10)
        plot_growth(ax, growth)
        legend_elements = [
            Line2D([0], [0], marker="o", color="w", markerfacecolor="#FF0033", markersize=8, label="MTG detections"),
            Line2D([0], [0], color="black", lw=3, label="Previous perimeter"),
            Patch(facecolor="orange", edgecolor="orange", alpha=1.0, label="Hourly growth"),
            Line2D([0], [0], color="deepskyblue", lw=1.2, label="Rivers / Watercourses"),
            Line2D([0], [0], marker="^", color="w", markerfacecolor="royalblue", markeredgecolor="white", markersize=9, linestyle="None", label="Populated places")]
        ax_leg = fig.add_axes([0.85, 0.72, 0.14, 0.20])
        ax_leg.axis("off")
        ax_leg.legend(handles=legend_elements, loc="upper left", framealpha=0.95, fontsize=12, borderpad=0.3, labelspacing=0.4, handlelength=1.2)
        ax.text(0.02, 0.98, f"ΔA = {dA:.1f} ha", transform=ax.transAxes, fontsize=12, ha="left", va="top", zorder=1000, bbox=dict(facecolor="white", edgecolor="black", boxstyle="round,pad=0.4", alpha=0.90))
        ax.set_title(f"{fire_name}\n{t1:%Y-%m-%d %H:%M}  →  {t2:%Y-%m-%d %H:%M}")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.grid(alpha=0.25)
        _set_map_axes(ax, limits)
        _add_dem_colorbar(fig, im_dem, [0.90, 0.14, 0.015, 0.55])
        _add_footer(fig, run_time)
        _save_frame(fig, daily_pngs, snapshot_dir, f"{fire_name}_Perimeter_", t1)
        print(f"Map {i}/{len(frames)} processed: {t1:%Y-%m-%d %H:%M}")
    _finish_daily_gif(daily_pngs, current_day, gif_dir, fire_name)
    print("\nPerimeter maps completed.\n")
# OUTPUT 2: LAND COVER + PERIMETER
def plot_landcover_maps(df_fire, shapes, lc_plot, extent_dem, cmap_lc, norm_lc, labels, output_dir, start,
    end, fire_name="Wildfire", logo_ipma=None, logo_lsa=None, run_time=None, analysis_data=None, frames=None):
    gif_dir, snapshot_dir = _prepare_output_dirs(output_dir)
    daily_pngs = []
    current_day = None
    analysis_data, frames = _prepare_frames(df_fire, shapes, start, end, analysis_data, frames)
    limits = get_map_limits(shapes)
    print("Creating land cover maps...")
    print(f"Maps to create: {len(frames)}")
    for i, frame in enumerate(frames, start=1):
        t1, t2 = frame["T1"], frame["T2"]
        daily_pngs, current_day = _update_daily_gif(daily_pngs, current_day, t1.normalize(), gif_dir, fire_name)
        shape_old, growth = frame["SHAPE_OLD"], frame["GROWTH"]
        fig = plt.figure(figsize=(16, 10))
        add_logos(fig, logo_ipma, logo_lsa, ipma_position=(0.45, 0.03), lsa_position=(0.52, 0.03))
        ax = fig.add_axes([0.06, 0.10, 0.78, 0.80])
        ax.imshow(lc_plot, cmap=cmap_lc, norm=norm_lc, extent=extent_dem, interpolation="nearest", aspect="auto")
        plot_shape(ax, shape_old, color="white", linewidth=3, zorder=20)
        plot_growth(ax, growth)
        history = frame["HISTORY"]
        ax.scatter(history["LONGITUDE"], history["LATITUDE"], color="white", s=200, alpha=1.0, zorder=25)
        _set_map_axes(ax, limits)
        ax.set_title(f"{fire_name}\nLand Cover - {t1:%Y-%m-%d %H:%M}  →  {t2:%H:%M} UTC")
        legend_elements = [
            Line2D([0], [0], color="white", lw=3, label="Previous perimeter"),
            Line2D([0], [0], marker="o", color="white", markerfacecolor="white", markersize=8, linestyle="None", label="MTG detections"),
            Patch(facecolor="orange", edgecolor="orange", alpha=1.0, label="Hourly growth")]
        ax.legend(handles=legend_elements, loc="upper right", framealpha=0.95, facecolor="dimgray", edgecolor="white", labelcolor="white", fontsize=11)
        _add_landcover_colorbar(fig, cmap_lc, norm_lc, labels, [0.87, 0.10, 0.025, 0.68])
        _add_footer(fig, run_time)
        _save_frame(fig, daily_pngs, snapshot_dir, f"{fire_name}_LandCover_", t1)
        print(f"Map {i}/{len(frames)} processed: {t1:%Y-%m-%d %H:%M}")
    _finish_daily_gif(daily_pngs, current_day, gif_dir, fire_name)
    print("Land cover maps completed.")
# OUTPUT 3: LAND COVER + PERIMETER + BURNED AREA
def plot_landcover_burned_area_maps(df_fire, shapes, lc_plot, extent_dem, cmap_lc, norm_lc, labels,
    last_burn_crop, last_burn_extent, burn_cmap, burn_norm, output_dir, start, end, fire_name="Wildfire",
    logo_ipma=None, logo_lsa=None, run_time=None, analysis_data=None, frames=None):
    gif_dir, snapshot_dir = _prepare_output_dirs(output_dir)
    daily_pngs = []
    current_day = None
    analysis_data, frames = _prepare_frames(df_fire, shapes, start, end, analysis_data, frames)
    limits = get_map_limits(shapes)
    burn_plot = np.ma.masked_invalid(last_burn_crop)
    burn_boundaries = np.arange(2020.5, 2026.5, 1)
    burn_ticks = np.arange(2021, 2026)
    print("Creating land cover + burned area maps...")
    print(f"Maps to create: {len(frames)}")
    for i, frame in enumerate(frames, start=1):
        t1, t2 = frame["T1"], frame["T2"]
        daily_pngs, current_day = _update_daily_gif(daily_pngs, current_day, t1.normalize(), gif_dir, fire_name)
        shape_old, growth = frame["SHAPE_OLD"], frame["GROWTH"]
        fig = plt.figure(figsize=(17.5, 10.5))
        add_logos(fig, logo_ipma, logo_lsa, ipma_position=(0.465, 0.045), lsa_position=(0.535, 0.045))
        ax = fig.add_axes([0.045, 0.14, 0.713, 0.762])
        ax.imshow(lc_plot, cmap=cmap_lc, norm=norm_lc, extent=extent_dem, interpolation="nearest", aspect="auto")
        ax.imshow(burn_plot, extent=last_burn_extent, origin="upper", cmap=burn_cmap, norm=burn_norm, interpolation="nearest", zorder=5)
        plot_shape(ax, shape_old, color="white", linewidth=3, zorder=20)
        plot_growth(ax, growth)
        history = frame["HISTORY"]
        ax.scatter(history["LONGITUDE"], history["LATITUDE"], color="white", s=200, alpha=1.0, zorder=25)
        legend_elements = [
            Line2D([0], [0], color="white", lw=3, label="Previous perimeter"),
            Line2D([0], [0], marker="o", color="white", markerfacecolor="white", markersize=8, linestyle="None", label="MTG detections"),
            Patch(facecolor="orange", edgecolor="orange", alpha=1.0, label="Growth")]
        ax.legend(handles=legend_elements, loc="upper right", framealpha=0.95, facecolor="dimgray", edgecolor="white", labelcolor="white", fontsize=11)
        _set_map_axes(ax, limits)
        ax.set_title(f"{fire_name}\nLand Cover + Previous Burn Year - {t1:%Y-%m-%d %H:%M} UTC")
        _add_landcover_colorbar(fig, cmap_lc, norm_lc, labels, [0.785, 0.14, 0.025, 0.762])
        cb_burn = ColorbarBase(fig.add_axes([0.905, 0.14, 0.025, 0.762]), cmap=burn_cmap, norm=burn_norm, boundaries=burn_boundaries, ticks=burn_ticks)
        cb_burn.set_label("Previous Burn Year")
        cb_burn.ax.tick_params(labelsize=9)
        _add_footer(fig, run_time)
        _save_frame(fig, daily_pngs, snapshot_dir, f"{fire_name}_LandCover_BurnedArea_", t1)
        print(f"Map {i}/{len(frames)} processed.")
    _finish_daily_gif(daily_pngs, current_day, gif_dir, fire_name)
    print("Land cover + burned area maps completed.")
# OUTPUT 4: ACTIVITY + PERIMETER + ALTITUDE + RIVERS + POPULATION
def plot_activity_maps(df_fire, shapes, dem, extent_dem, rivers, places, output_dir, start, end, fire_name="Wildfire",
    logo_ipma=None, logo_lsa=None, run_time=None, analysis_data=None, frames=None):
    gif_dir, snapshot_dir = _prepare_output_dirs(output_dir)
    daily_pngs = []
    current_day = None
    analysis_data, frames = _prepare_frames(df_fire, shapes, start, end, analysis_data, frames)
    limits = get_map_limits(shapes)
    period_colors = {"Day": "#F2B705", "Sunset": "#E85D04", "Night": "#2F5597"}
    print("Creating activity maps...")
    print(f"Maps to create: {len(frames)}")
    for i, frame in enumerate(frames, start=1):
        t1 = frame["T1"]
        daily_pngs, current_day = _update_daily_gif(daily_pngs, current_day, t1.normalize(), gif_dir, fire_name)
        history = frame["HISTORY"].copy()
        fig = plt.figure(figsize=(18, 10))
        add_logos(fig, logo_ipma, logo_lsa)
        ax = fig.add_axes([0.04, 0.11, 0.78, 0.84])
        im_dem = ax.imshow(dem, cmap="Greys", extent=extent_dem)
        ax.set_aspect("auto", adjustable="box")
        _plot_rivers(ax, rivers)
        _plot_places(ax, places)
        history["PERIOD"] = history["ACQTIME"].dt.hour.apply(classify_period)
        for period, color in period_colors.items():
            data_period = history[history["PERIOD"] == period]
            if not data_period.empty:
                ax.scatter(data_period["LONGITUDE"], data_period["LATITUDE"], color=color, s=200, alpha=1.0, zorder=10)
        legend_elements = [
            Line2D([0], [0], marker="o", color="w", markerfacecolor="#F2B705", markersize=9, label="Day"),
            Line2D([0], [0], marker="o", color="w", markerfacecolor="#E85D04", markersize=9, label="Sunset"),
            Line2D([0], [0], marker="o", color="w", markerfacecolor="#2F5597", markersize=9, label="Night"),
            Line2D([0], [0], color="deepskyblue", lw=1.2, label="Rivers / Watercourses"),
            Line2D([0], [0], marker="^", color="w", markerfacecolor="royalblue", markeredgecolor="white", markersize=9, linestyle="None", label="Populated places")]
        ax_leg = fig.add_axes([0.83, 0.60, 0.16, 0.32])
        ax_leg.axis("off")
        ax_leg.legend(handles=legend_elements, loc="upper left", framealpha=0.95, fontsize=10, borderpad=0.3, labelspacing=0.5, handlelength=1.2)
        _set_map_axes(ax, limits)
        ax.set_title(f"{fire_name}\n{t1:%Y-%m-%d %H:%M} UTC")
        _add_dem_colorbar(fig, im_dem, [0.86, 0.14, 0.015, 0.55])
        _add_footer(fig, run_time)
        _save_frame(fig, daily_pngs, snapshot_dir, f"{fire_name}_Activity_", t1)
        print(f"Map {i}/{len(frames)} processed.")
    _finish_daily_gif(daily_pngs, current_day, gif_dir, fire_name)
    print("Activity maps completed.")
