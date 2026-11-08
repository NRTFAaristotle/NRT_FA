"""
download.py
"""
from pathlib import Path
from io import BytesIO
from datetime import timedelta
import xarray as xr
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_FOLDER = PROJECT_ROOT / "data" / "raw"

def build_url(tslot):

    return (
        "https://datalsasaf.lsasvcs.ipma.pt/"
        f"PRODUCTS/MTG/MTFRPPixel/NATIVE/"
        f"{tslot:%Y/%m/%d}/"
        f"LSA-509_MTG_MTFRPPIXEL-ListProduct_MTG-FD_{tslot:%Y%m%d%H%M}.csv.gz")

def local_filename(tslot):
    return DATA_FOLDER / "frp" / f"{tslot:%Y%m%d%H%M}.csv.gz"

def download_file(tslot, user, password):

    filename = local_filename(tslot)
    filename.parent.mkdir(parents=True, exist_ok=True)
    if filename.exists():
        print(f"[CACHE] {filename.name}")
        return pd.read_csv(filename, compression="gzip")

    url = build_url(tslot)
    try:
        r = requests.get(url,auth=(user, password),timeout=30)
        if r.status_code != 200:
            print(f"[SKIP] {tslot}")
            return None
        filename.write_bytes(r.content)
        print(f"[OK] {filename.name}")
        return pd.read_csv(BytesIO(r.content),compression="gzip")
    except Exception as e:
        print(f"[ERRO] {tslot} -> {e}")
        return None

def download_period(start, end, user, password):
    current = start
    dfs = []
    while current <= end:
        df = download_file(current,user,password)
        if df is not None:
            dfs.append(df)
        current += timedelta(minutes=10)
    if len(dfs) == 0:
        raise ValueError("Nenhum ficheiro foi encontrado.")
    return pd.concat(dfs,ignore_index=True)
def build_frem_url(tslot):
    return (
        "https://datalsasaf.lsasvcs.ipma.pt/"
        f"PRODUCTS/MSG/FREM/NETCDF/"
        f"{tslot:%Y/%m/%d}/"
        f"NETCDF4_LSASAF_MSG_FREM_MSG-Disk_"
        f"{tslot:%Y%m%d%H00}.nc")

def local_frem_filename(tslot):
    return DATA_FOLDER / "frem" / f"{tslot:%Y%m%d%H00}.nc"
def download_frem_file(tslot, user, password):
    filename = local_frem_filename(tslot)
    filename.parent.mkdir(parents=True, exist_ok=True)
    if filename.exists():
        print(f"[CACHE FREM] {filename.name}")
        return xr.open_dataset(filename, group="FRE")
    url = build_frem_url(tslot)
    try:
        r = requests.get(url,auth=(user, password),timeout=30)
        if r.status_code != 200:
            print(f"[SKIP FREM] {tslot}")
            return None
        filename.write_bytes(r.content)
        print(f"[OK FREM] {filename.name}")
        return xr.open_dataset(filename,group="FRE")
    except Exception as e:
        print(f"[ERRO FREM] {tslot} -> {e}")
        return None
def download_frem_period(start, end, user, password):
    current = start.replace(minute=0,second=0,microsecond=0)
    datasets = []
    while current <= end:
        ds = download_frem_file(current,user,password)
        if ds is not None:
            datasets.append(ds)
        current += timedelta(hours=1)
    if len(datasets) == 0:
        raise ValueError("Nenhum ficheiro FREM foi encontrado.")
    return xr.concat(datasets,dim="time")