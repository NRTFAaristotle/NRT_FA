"""
Layout
"""
import numpy as np
import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cf
import imageio.v2 as imageio
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from PIL import Image
from pathlib import Path
from matplotlib.gridspec import GridSpec
from cartopy.io.img_tiles import OSM

#OPEN STREET MAP
tiler = OSM()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FOLDER = PROJECT_ROOT / "output"
GIF_FOLDER = OUTPUT_FOLDER / "gifs"

def plot_bottom_info(ax,hour,df_fire,shape,ros_row):
    ax.axis("off")
    history=df_fire[df_fire["ACQTIME"]<=hour]
    current=df_fire[df_fire["HOUR"]==hour]
    active_pixels=len(current)
    current_frp=current["FRP"].sum()
    fre_gj=(history["FRP"].sum()*600/1000)
    area=0
    if shape is not None:
        area=(gpd.GeoSeries([shape],crs="EPSG:4326").to_crs("EPSG:3035").area.iloc[0]/10000)
    ros=0
    if ros_row is not None:
        ros=ros_row["ROS_MAX_m_h"]
    text=(
        f"Time: {hour:%d %b %Y %H:%M UTC}     "
        f"Active Pixels: {active_pixels}     "
        f"Current FRP: {current_frp:.0f} MW     "
        f"Accumulated FRE: {fre_gj:.0f} GJ     "
        f"Fire Area: {area:.0f} ha     "
        f"Maximum ROS: {ros:.0f} m/h")
    ax.text(0.5,0.5,text,ha="center",va="center",fontsize=14,fontweight="bold")

def create_information_table(df_fire, shapes, ros_df):
    rows = []
    for i, item in enumerate(shapes):
        hour = item["HOUR"]
        shape = item["SHAPE"]
        history = df_fire[df_fire["ACQTIME"] <= hour]
        current = df_fire[df_fire["HOUR"] == hour]
        active_pixels = len(current)
        current_frp = current["FRP"].sum()
        fre_gj = history["FRP"].sum() * 600 / 1000
        area = 0
        if shape is not None:
            area = (gpd.GeoSeries([shape], crs="EPSG:4326").to_crs("EPSG:3035").area.iloc[0]/10000)
        ros = 0
        if i > 0:
            ros_row = ros_df[ros_df["HOUR"] == hour]
            if len(ros_row):
                ros = ros_row.iloc[0]["ROS_MAX_m_h"]
        rows.append({
            "Time (UTC)": hour,
            "Active Pixels": active_pixels,
            "Current FRP (MW)": current_frp,
            "Accumulated FRE (GJ)": fre_gj,
            "Fire Area (ha)": area,
            "Maximum ROS (m/h)": ros})
    return pd.DataFrame(rows)

def plot_fire_map(ax,df_fire,shape,ros_row,hour,frp_max,extent):
    history=df_fire[df_fire["ACQTIME"]<=hour]
    df_map=( history.groupby(["LATITUDE","LONGITUDE"])["FRP"].max().reset_index())
    sc=ax.scatter(df_map["LONGITUDE"],df_map["LATITUDE"],c=df_map["FRP"],
        cmap="hot_r",s=50,vmin=0,vmax=frp_max,transform=ccrs.PlateCarree(),zorder=2)

    if shape is not None:
        if shape.geom_type=="Polygon":
            x,y=shape.exterior.xy
            ax.plot(x, y, color="black", linewidth=2, transform=ccrs.PlateCarree(), zorder=10)
        elif shape.geom_type=="MultiPolygon":
            for poly in shape.geoms:
                x,y=poly.exterior.xy
                ax.plot(x,y,color="black",linewidth=2,transform=ccrs.PlateCarree(),zorder=10)
    if ros_row is not None:
        curr=ros_row["CURR_POINT"]
        prev=ros_row["PREV_POINT"]
        if curr is not None and prev is not None:
            pts=(gpd.GeoSeries([curr,prev],crs="EPSG:3035").to_crs("EPSG:4326"))
            curr=pts.iloc[0]
            prev=pts.iloc[1]
            ax.plot([prev.x,curr.x],[prev.y,curr.y],color="lime", linewidth=3,transform=ccrs.PlateCarree(),zorder=20)
            ax.scatter(prev.x,prev.y,color="purple",s=90,edgecolor="white",transform=ccrs.PlateCarree(),zorder=21)
            ax.scatter(curr.x,curr.y,color="deeppink",s=90,edgecolor="white",transform=ccrs.PlateCarree(),zorder=22)
    ax.coastlines("10m")
    ax.add_feature(cf.BORDERS,linewidth=0.7)
    gl = ax.gridlines(draw_labels=True, linestyle="--", alpha=0.4)
    gl.right_labels = False
    ax.set_extent(extent,crs=ccrs.PlateCarree())

    ax.add_image(tiler, 12)
    ax.set_title("Fire Perimeter")
    return sc
def plot_pixels_frp(ax,df_fire,current_hour):
    all_hours=pd.date_range(start=df_fire["HOUR"].min(),end=df_fire["HOUR"].max(),freq="1h")
    stats=( df_fire.groupby("HOUR").agg(PIXELS=("FRP","count"),FRP=("FRP","sum"))
        .reindex(all_hours,fill_value=0).rename_axis("HOUR").reset_index())
    ax.bar(
        stats["HOUR"],
        stats["PIXELS"],
        width=0.03,
        color="steelblue",
        edgecolor="black",
        linewidth=0.5)
    ax.set_ylabel("Nº Pixels")
    ax2=ax.twinx()
    ax2.plot(stats["HOUR"],stats["FRP"],color="darkorange",linewidth=2)
    current=stats[stats["HOUR"]==current_hour]
    if len(current):
        ax2.scatter(
            current["HOUR"],
            current["FRP"],
            color="red",
            s=100,
            zorder=20)
    idx=(stats["HOUR"]-current_hour).abs().idxmin()
    ax2.scatter(
        stats.loc[idx,"HOUR"],
        stats.loc[idx,"FRP"],
        color="red",
        s=100,
        zorder=20)
    ax2.set_ylabel("FRP (MW)")
    ax.set_title("Hourly Fire Activity")
    plt.setp(ax.get_xticklabels(),rotation=45,ha="right")
def plot_ros_timeseries(ax,ros_df,current_hour):
    ax.plot(
        ros_df["HOUR"],
        ros_df["ROS_MAX_m_h"],
        color="royalblue",
        linewidth=2,
        marker="o",
        markersize=4)
    history=ros_df[ros_df["HOUR"]<=current_hour]
    ax.fill_between(
        history["HOUR"],
        history["ROS_MAX_m_h"],
        alpha=0.2)
    current=ros_df[ros_df["HOUR"]==current_hour]
    if len(current):
        ax.scatter(
            current["HOUR"],
            current["ROS_MAX_m_h"],
            color="red",
            s=100,
            zorder=20)
    ax.grid(True,alpha=0.3)
    ax.set_title("Maximum Rate of Spread")
    ax.set_ylabel("ROS (m/h)")
    plt.setp(ax.get_xticklabels(),rotation=45,ha="right")
def create_frame(df_fire,shapes,ros_df,index,frp_max,extent):
    hour=shapes[index]["HOUR"]
    shape=shapes[index]["SHAPE"]
    ros_row=None
    if index>0:
        row=ros_df[ros_df["HOUR"]==hour]
        if len(row):
            ros_row=row.iloc[0]
    fig=plt.figure(figsize=(18,10))
    gs=GridSpec(2,3,height_ratios=[5,1],width_ratios=[2,1,1],left=0.05,right=0.95,
        top=0.95, bottom=0.13, wspace=0.18, hspace=0.08)
    ax_map=fig.add_subplot(gs[0,0],projection=ccrs.PlateCarree())
    ax_ros=fig.add_subplot(gs[0,1])
    ax_stats=fig.add_subplot(gs[0,2])
    ax_info=fig.add_subplot(gs[1,:])
    sc=plot_fire_map(ax_map,df_fire,shape,ros_row,hour,frp_max,extent)
    plot_ros_timeseries(ax_ros,ros_df,hour)
    plot_pixels_frp(ax_stats,df_fire,hour)
    plot_bottom_info(ax_info,hour,df_fire,shape,ros_row)
    logo_ipma = Image.open("IPMA.jpg")
    logo_lsasaf = Image.open("LSA_SAF.png")
    img_ipma = OffsetImage(logo_ipma, zoom=0.2)
    img_lsasaf = OffsetImage(logo_lsasaf, zoom=0.10)
    ab1 = AnnotationBbox(img_ipma,(0.43,0.04),xycoords="figure fraction",frameon=False)
    ab2 = AnnotationBbox(img_lsasaf,(0.56,0.04),xycoords="figure fraction",frameon=False)
    fig.add_artist(ab1)
    fig.add_artist(ab2)
    cbar=fig.colorbar(sc,ax=ax_map,orientation="horizontal",shrink=0.75, pad=0.12,fraction=0.05)
    cbar.set_label("FRP (MW)")
    fig.canvas.draw()
    img=np.asarray(fig.canvas.buffer_rgba())[:,:,:3]
    plt.close(fig)
    return img

def make_gif(df_fire, shapes, ros_df, output="FRP_Propagator.gif", fps=1):
    output = Path(output)
    if not output.is_absolute() and output.parent == Path("."):
        output = GIF_FOLDER / output
    output.parent.mkdir(parents=True, exist_ok=True)
    df_information = create_information_table(df_fire, shapes, ros_df)
    csv_output = output.with_name(f"{output.stem}_information.csv")
    df_information.to_csv(csv_output,index=False,na_rep="NULL")
    frp_max = df_fire["FRP"].quantile(0.99)
    extent = [
        df_fire["LONGITUDE"].min() - 0.05,
        df_fire["LONGITUDE"].max() + 0.05,
        df_fire["LATITUDE"].min() - 0.05,
        df_fire["LATITUDE"].max() + 0.05]
    frames = []
    for i in range(len(shapes)):
        if shapes[i]["SHAPE"] is None:
            continue
        print(f"Frame {i+1}/{len(shapes)}")
        frame = create_frame(df_fire, shapes, ros_df, i, frp_max, extent)
        frames.append(frame)
    imageio.mimsave(output, frames, fps=fps, loop=0)
    print()
    print("==============================")
    print("GIF criado com sucesso!")
    print(output)
    print("==============================")