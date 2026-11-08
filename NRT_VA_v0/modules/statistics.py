"""
statistics.py
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

def hourly_statistics(df):
    df=df.copy()
    df["DATE"]=df["HOUR"].dt.normalize()
    days=pd.date_range(df["DATE"].min(),df["DATE"].max(),freq="1D")
    rows=[]
    for day in days:
        day_df=df[df["DATE"]==day]
        for hour in range(24):
            hour_df=day_df[day_df["HOUR"].dt.hour==hour]
            if len(hour_df)==0:
                frp=np.nan
                fre=np.nan
            else:
                frp=hour_df["FRP"].max()
                fre=frp*600/1000
            rows.append({
                "DATE":day.date(),
                "HOUR":hour,
                "MAX_FRP_MW":frp,
                "MAX_FRE_GJ":fre})
    return pd.DataFrame(rows)
def daily_statistics(df):
    df=df.copy()
    df["DATE"]=df["ACQTIME"].dt.normalize()
    stats=(df.groupby("DATE").agg(FRP_ACC_MW=("FRP","sum")).reset_index())
    stats["FRE_ACC_GJ"]=(stats["FRP_ACC_MW"]*600/1000)
    stats["DATE"]=stats["DATE"].dt.date
    return stats

def plot_hourly_statistics(hourly_stats, output=None):
    df = hourly_stats.copy()
    df["DATE"] = pd.to_datetime(df["DATE"])
    df["DATETIME"] = (df["DATE"] +pd.to_timedelta(df["HOUR"], unit="h"))
    df = df.sort_values("DATETIME")
    fig, ax1 = plt.subplots(figsize=(16, 6))
    ax1.plot(df["DATETIME"],df["MAX_FRP_MW"],color="red",marker="o",linewidth=2,label="FRP",zorder=10)
    ax1.set_ylabel("Maximum FRP (MW)",fontsize=12)
    ax1.tick_params(axis="y", colors="red")
    ax1.set_ylim(0,df["MAX_FRP_MW"].max() * 1.2)
    ax2 = ax1.twinx()
    ax1.set_zorder(ax2.get_zorder() + 1)
    ax1.patch.set_visible(False)
    ax2.plot(df["DATETIME"],df["MAX_FRE_GJ"],color="green",marker="s",linewidth=2,label="FRE",zorder=1)
    ax2.set_ylabel("Maximum FRE (GJ)",fontsize=12)
    ax2.tick_params(axis="y", colors="green")
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m\n%H:%M"))
    plt.xticks(rotation=90)
    ax1.grid(alpha=0.3)
    plt.title("Hourly Maximum FRP and FRE")
    plt.tight_layout()
    if output is not None:
        plt.savefig(output, dpi=300, bbox_inches="tight")
    #plt.show()
    return fig

def run_statistics(df_fire, output_name, output_folder="output/statistics"):
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    hourly_stats = hourly_statistics(df_fire)
    daily_stats = daily_statistics(df_fire)

    hourly_stats.to_csv(output_folder / f"{output_name}_hourly_statistics.csv",na_rep="NULL",index=False)
    daily_stats.to_csv(output_folder / f"{output_name}_daily_statistics.csv",index=False)

    plot_hourly_statistics(hourly_stats,output=output_folder / f"{output_name}_hourly_statistics.png")
    return hourly_stats, daily_stats