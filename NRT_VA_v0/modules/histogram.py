"""
histogram.py
"""

import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

def hourly_histogram_stats(df_fire, day):
    df_day = df_fire[df_fire["HOUR"].dt.date == day.date()]
    hours = pd.date_range(start=pd.Timestamp(day),periods=24,freq="1h")
    stats = (df_day.groupby("HOUR").agg(PIXELS=("FRP","count"),FRP=("FRP","sum")))
    stats = (stats.reindex(hours, fill_value=0).rename_axis("HOUR").reset_index())
    return stats

def plot_daily_histogram(df_fire,day):
    stats = hourly_histogram_stats(df_fire,day)
    fig,ax = plt.subplots(figsize=(12,5))

    ax.bar(stats["HOUR"].dt.hour,stats["PIXELS"],color="grey",edgecolor="black")
    ax.set_xlabel("Hour UTC")
    ax.set_ylabel("Number of FRP pixels")
    ax.set_xticks(range(24))
    ax.grid(alpha=0.3)

    ax2=ax.twinx()
    ax2.plot(stats["HOUR"].dt.hour,stats["FRP"],color="darkorange",linewidth=2,marker="o")
    ax2.set_ylabel("Hourly FRP (MW)")
    ax.set_title(f"Fire activity {day.strftime('%d-%m-%Y')}")
    plt.tight_layout()
    return fig

def plot_all_days_histograms(df_fire,output_name,output_folder="output/histograms"):
    output_folder=Path(output_folder)
    output_folder.mkdir(parents=True,exist_ok=True)
    days=df_fire["HOUR"].dt.date.unique()
    figs=[]
    for day in sorted(days):
        day=pd.Timestamp(day)
        print(f"Histogram {day:%d-%m-%Y}")
        fig=plot_daily_histogram(df_fire,day)
        fig.savefig(output_folder/f"{output_name}_{day:%Y%m%d}.png",dpi=300,bbox_inches="tight")
        figs.append(fig)
    return figs