"""
processing.py
"""
import pandas as pd

def prepare_dataframe(df):
    df = df.copy()

    if not pd.api.types.is_datetime64_any_dtype(df["ACQTIME"]):
        try:
            df["ACQTIME"] = pd.to_datetime(df["ACQTIME"],format="%Y%m%d%H%M%S")
    
        except Exception:
            df["ACQTIME"] = pd.to_datetime(df["ACQTIME"],format="mixed")
    df = df.sort_values("ACQTIME")
    df = df.reset_index(drop=True)
    df["HOUR"] = df["ACQTIME"].dt.floor("h")
    return df

def select_area(df,lat_min,lat_max,lon_min,lon_max):
    df_fire = df[
        (df["LATITUDE"] >= lat_min) &
        (df["LATITUDE"] <= lat_max) &
        (df["LONGITUDE"] >= lon_min) &
        (df["LONGITUDE"] <= lon_max)].copy()
    df_fire = df_fire.reset_index(drop=True)
    return df_fire

def select_area_frem(ds,lat_min,lat_max,lon_min,lon_max):
    ds_area = ds.sel(lat=slice(lat_min, lat_max),lon=slice(lon_min, lon_max))
    return ds_area
     