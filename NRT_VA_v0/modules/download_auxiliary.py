from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple
import logging
import math
import imageio.v2 as imageio
import numpy as np
import requests
import rasterio
from contextlib import ExitStack
from rasterio.merge import merge

LOG = logging.getLogger(__name__)
CORINE_2018_EXPORT = ( "https://image.discomap.eea.europa.eu/arcgis/rest/services/" "Corine/CLC2018_WM/MapServer/export")
MAX_IMAGE_SIZE = 4096
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
@dataclass
class RasterLayer:
    data: np.ndarray
    extent: Tuple[float, float, float, float]
    name: str = ""
CLC = {
    111: ("Continuous urban", "#e6004d"),
    112: ("Discontinuous urban", "#ff0000"),
    121: ("Industrial/commercial", "#cc4df2"),
    122: ("Road/rail", "#cc0000"),
    123: ("Port", "#e6cccc"),
    124: ("Airport", "#e6cce6"),
    131: ("Mineral extraction", "#a600cc"),
    132: ("Dump site", "#a64d00"),
    133: ("Construction", "#ff4dff"),
    141: ("Green urban", "#ffa6ff"),
    142: ("Sport/leisure", "#ffe6ff"),
    211: ("Non-irrigated arable", "#ffffa8"),
    212: ("Irrigated arable", "#ffff00"),
    213: ("Rice fields", "#e6e600"),
    221: ("Vineyards", "#e68000"),
    222: ("Fruit/berry plantations", "#f2a64d"),
    223: ("Olive groves", "#e6a600"),
    231: ("Pastures", "#e6e64d"),
    241: ("Annual/permanent crops", "#ffe6a6"),
    242: ("Complex cultivation", "#ffe64d"),
    243: ("Agriculture+natural veg.", "#e6cc4d"),
    244: ("Agro-forestry", "#f2cca6"),
    311: ("Broad-leaved forest", "#80ff00"),
    312: ("Coniferous forest", "#00a600"),
    313: ("Mixed forest", "#4dff00"),
    321: ("Natural grassland", "#ccf24d"),
    322: ("Moors/heathland", "#a6ff80"),
    323: ("Sclerophyllous veg.", "#a6e64d"),
    324: ("Trans. woodland/shrub", "#a6f200"),
    331: ("Beaches/dunes", "#e6e6e6"),
    332: ("Bare rock", "#cccccc"),
    333: ("Sparse veg.", "#ccffcc"),
    335: ("Glacier/snow", "#a6e6cc"),
    411: ("Inland marsh", "#a6a6ff"),
    412: ("Peat bog", "#4d4dff"),
    421: ("Salt marsh", "#ccccff"),
    422: ("Saline", "#e6e6ff"),
    423: ("Intertidal flat", "#a6a6e6"),
    511: ("Watercourse", "#00ccf2"),
    512: ("Water body", "#80f2e6"),
    521: ("Coastal lagoon", "#00ffa6"),
    522: ("Estuary", "#a6ffe6"),
    523: ("Sea/ocean", "#e6f2ff")}
def _read_valid_png(path: Path) -> Optional[np.ndarray]:
    try:
        if not path.is_file() or path.stat().st_size <= len(PNG_SIGNATURE):
            return None
        with path.open("rb") as file:
            if file.read(len(PNG_SIGNATURE)) != PNG_SIGNATURE:
                return None
        image = imageio.imread(path)
    except (OSError, ValueError, RuntimeError):
        return None
    if ( image.ndim != 3 or image.shape[0] == 0 or image.shape[1] == 0 or image.shape[2] not in (3, 4)):
        return None
    return image

def _decode_corine_classes(image: np.ndarray) -> Optional[np.ndarray]:
    rgb = image[:, :, :3]
    if image.shape[2] == 4:
        valid_pixels = image[:, :, 3] > 0
    else:
        valid_pixels = np.ones(rgb.shape[:2], dtype=bool)
    classes = np.full(rgb.shape[:2], np.nan, dtype=float)
    for code, (_, color) in CLC.items():
        triplet = np.array( [int(color[i:i + 2], 16) for i in (1, 3, 5)], dtype=np.uint8,)
        matches = np.all(rgb == triplet, axis=2) & valid_pixels
        classes[matches] = code
    if not np.isfinite(classes).any():
        return None
    return classes

def download_corine2018(bounds,cache_dir: Path,session: requests.Session) -> Optional[RasterLayer]:
    try:
        xmin, ymin, xmax, ymax = map(float, bounds)
    except (TypeError, ValueError) as exc:
        raise ValueError( "bounds must contain xmin, ymin, xmax and ymax." ) from exc
    if not (-180 <= xmin < xmax <= 180 and -90 <= ymin < ymax <= 90):
        raise ValueError("Invalid geographic bounds.")
    cache_path = Path(cache_dir) / "corine2018"
    cache_path.mkdir(parents=True, exist_ok=True)
    key = ( f"{xmin:.5f}_{ymin:.5f}_{xmax:.5f}_{ymax:.5f}").replace("-", "m")
    destination = cache_path / f"clc_{key}.png"
    image = _read_valid_png(destination)
    if image is not None:
        LOG.info("Using cached CORINE image: %s", destination.name)
    else:
        destination.unlink(missing_ok=True)
        mean_lat = (ymin + ymax) / 2
        width = max( 2,round( (xmax - xmin) * 111_320 * math.cos(math.radians(mean_lat)) / 100 ),)
        height = max( 2,round((ymax - ymin) * 110_540 / 100),)
        scale = min( 1.0, MAX_IMAGE_SIZE / max(width, height),)
        width = max(2, round(width * scale))
        height = max(2, round(height * scale))
        params = {
            "bbox": f"{xmin},{ymin},{xmax},{ymax}",
            "bboxSR": "4326",
            "imageSR": "4326",
            "size": f"{width},{height}",
            "format": "png32",
            "transparent": "true",
            "layers": "show:1",
            "dpi": "96",
            "adjustAspectRatio": "false",
            "f": "image",}
        temporary = destination.with_name( f"{destination.stem}.part.png")
        try:
            try:
                with session.get( CORINE_2018_EXPORT, params=params, timeout=(15, 180),) as response:
                    response.raise_for_status()
                    content = response.content
            except requests.RequestException as exc:
                LOG.warning("Could not obtain CORINE 2018: %s", exc)
                return None
            if not content.startswith(PNG_SIGNATURE):
                LOG.warning("CORINE service did not return a PNG.")
                return None
            temporary.write_bytes(content)
            image = _read_valid_png(temporary)
            if image is None:
                LOG.warning("Downloaded CORINE image is invalid.")
                return None
            temporary.replace(destination)
            LOG.info( "Downloaded CORINE 2018: %s (%d x %d pixels)", destination.name, width, height,)
        finally:
            temporary.unlink(missing_ok=True)
    classes = _decode_corine_classes(image)
    if classes is None:
        LOG.warning("No CORINE classes could be decoded for %s", destination)
        return None
    number_of_classes = len(np.unique(classes[np.isfinite(classes)]))
    LOG.info( "Decoded %d CORINE pixels across %d classes", int(np.isfinite(classes).sum()), number_of_classes,)
    # Obtain the actual geographic extent of the exported image
    image_height, image_width = image.shape[:2]
    extent_params = {
        "bbox": f"{xmin},{ymin},{xmax},{ymax}",
        "bboxSR": "4326",
        "imageSR": "4326",
        "size": f"{image_width},{image_height}",
        "format": "png32",
        "transparent": "true",
        "layers": "show:1",
        "dpi": "96",
        "adjustAspectRatio": "false",
        "f": "json",}
    try:
        with session.get(CORINE_2018_EXPORT,params=extent_params,timeout=(15, 30),) as response:
            response.raise_for_status()
            metadata = response.json()
        service_extent = metadata.get("extent")
        if not service_extent:
            raise ValueError("The CORINE service did not return a geographic extent.")
        spatial_reference = service_extent.get("spatialReference", {})
        wkid = spatial_reference.get("latestWkid",spatial_reference.get("wkid"))
        if wkid is not None and int(wkid) != 4326:
            raise ValueError(f"Unexpected CORINE coordinate system: {wkid}")
        actual_extent = (
            float(service_extent["xmin"]),
            float(service_extent["xmax"]),
            float(service_extent["ymin"]),
            float(service_extent["ymax"]),)
    except (requests.RequestException, ValueError,KeyError,TypeError,) as exc:
        LOG.warning( "Could not obtain the actual CORINE extent: %s", exc)
        return None

    return RasterLayer(data=classes,extent=actual_extent,name="CORINE Land Cover 2018",)

DEM_URL=("https://copernicus-dem-30m.s3.amazonaws.com/""Copernicus_DSM_COG_10_{tile}_DEM/""Copernicus_DSM_COG_10_{tile}_DEM.tif")
def _dem_tile_name(lat,lon):
    return f"{'N' if lat>=0 else 'S'}{abs(lat):02d}_00_{'E' if lon>=0 else 'W'}{abs(lon):03d}_00"
def _valid_dem(path):
    try:
        with rasterio.open(path) as src:
            return src.width>0 and src.height>0 and src.count>=1 and src.crs is not None
    except (OSError,rasterio.errors.RasterioError,ValueError):
        return False
def download_dem_aoi(bounds,cache_dir,session=None):
    try:
        xmin,ymin,xmax,ymax=map(float,bounds)
    except (TypeError,ValueError) as exc:
        raise ValueError("bounds must be (xmin, ymin, xmax, ymax).") from exc
    if not (-180<=xmin<xmax<=180 and -90<=ymin<ymax<=90):
        raise ValueError("Invalid geographic bounds.")
    cache_dir=Path(cache_dir)
    aoi_dir=cache_dir/"dem"/"aoi"
    key="_".join(f"{v:.5f}" for v in (xmin,ymin,xmax,ymax)).replace("-","m")
    destination=aoi_dir/f"dem_aoi_{key}.tif"
    if _valid_dem(destination):
        LOG.info("Using cached DEM AOI: %s",destination.name)
        return destination
    destination.unlink(missing_ok=True)
    aoi_dir.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_name(f"{destination.stem}.part.tif")
    urls=[]
    for lat in range(math.floor(ymin),math.floor(ymax-1e-10)+1):
        for lon in range(math.floor(xmin),math.floor(xmax-1e-10)+1):
            tile=_dem_tile_name(lat,lon)
            urls.append("/vsicurl/"+DEM_URL.format(tile=tile))
    try:
        with ExitStack() as stack:
            sources=[stack.enter_context(rasterio.open(url)) for url in urls]
            mosaic,transform=merge(sources,bounds=(xmin,ymin,xmax,ymax))
            profile=sources[0].profile.copy()
            profile.update(
                driver="GTiff",
                height=mosaic.shape[1],
                width=mosaic.shape[2],
                transform=transform,
                count=1,
                compress="deflate",
                tiled=True)
            profile.pop("blockxsize",None)
            profile.pop("blockysize",None)
            with rasterio.open(temporary,"w",**profile) as output:
                output.write(mosaic[0],1)
        if not _valid_dem(temporary):
            raise ValueError("The cropped DEM mosaic is invalid.")
        temporary.replace(destination)
        LOG.info("Prepared DEM AOI using remote windows: %s",destination.name)
        return destination
    finally:
        temporary.unlink(missing_ok=True)

HYDRORIVERS_QUERY_URL="https://maps.fsc.org/server/rest/services/hosted/Optimized_Hyrdo/FeatureServer/0/query"
PROJECT_ROOT=Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR=PROJECT_ROOT/"data"/"raw"
def _valid_hydrorivers_gpkg(path):
    try:
        import geopandas as gpd
        if not path.is_file() or path.stat().st_size==0:
            return False
        rivers=gpd.read_file(path,layer="HydroRIVERS_v10_eu",rows=1)
        return rivers.crs is not None
    except Exception:
        return False

def download_hydrorivers(bounds,data_dir=DEFAULT_DATA_DIR,session=None):
    import geopandas as gpd
    from shapely.geometry import box

    try:
        xmin,ymin,xmax,ymax=map(float,bounds)
    except (TypeError,ValueError) as exc:
        raise ValueError("bounds must be (xmin, ymin, xmax, ymax).") from exc
    if not (-180<=xmin<xmax<=180 and -90<=ymin<ymax<=90):
        raise ValueError("Invalid geographic bounds.")
    data_dir=Path(data_dir)
    cache_dir=data_dir/"hydrorivers_aoi"
    key="_".join(f"{v:.6f}".replace("-","m").replace(".","p") for v in (xmin,ymin,xmax,ymax))
    destination=cache_dir/f"HydroRIVERS_{key}.gpkg"

    if _valid_hydrorivers_gpkg(destination):
        LOG.info("Using cached HydroRIVERS AOI: %s",destination.name)
        return destination
    cache_dir.mkdir(parents=True,exist_ok=True)
    destination.unlink(missing_ok=True)
    temporary=destination.with_name(destination.stem+".part.gpkg")
    temporary.unlink(missing_ok=True)
    own_session=session is None
    if own_session:
        session=requests.Session()

    def query(params):
        with session.get(HYDRORIVERS_QUERY_URL,params=params,timeout=(15,90)) as response:
            response.raise_for_status()
            result=response.json()
        if "error" in result:
            raise RuntimeError(f"HydroRIVERS API error: {result['error']}")
        return result
    try:
        result=query({
            "where":"1=1",
            "geometry":f"{xmin},{ymin},{xmax},{ymax}",
            "geometryType":"esriGeometryEnvelope",
            "inSR":4326,
            "spatialRel":"esriSpatialRelIntersects",
            "returnIdsOnly":"true",
            "returnGeometry":"false",
            "f":"json"})
        ids=result.get("objectIds") or []
        features=[]
        for start in range(0,len(ids),1000):
            batch=ids[start:start+1000]
            result=query({
                "objectIds":",".join(map(str,batch)),
                "outFields":"*",
                "returnGeometry":"true",
                "outSR":4326,
                "f":"geojson"})
            features.extend(result.get("features",[]))
        aoi=box(xmin,ymin,xmax,ymax)
        if features:
            rivers=gpd.GeoDataFrame.from_features(features,crs="EPSG:4326")
            rivers=rivers[rivers.geometry.notna() & ~rivers.geometry.is_empty].copy()
            if not rivers.empty:
                rivers=rivers[rivers.geometry.intersects(aoi)].copy()
                rivers.geometry=rivers.geometry.intersection(aoi)
                rivers=rivers[rivers.geometry.geom_type.isin(["LineString","MultiLineString"]) & ~rivers.geometry.is_empty].copy()
        else:
            rivers=gpd.GeoDataFrame({"geometry":gpd.GeoSeries([],crs="EPSG:4326")},crs="EPSG:4326")
        rivers.to_file(temporary,layer="HydroRIVERS_v10_eu",driver="GPKG",index=False)
        if not _valid_hydrorivers_gpkg(temporary):
            raise ValueError("Downloaded HydroRIVERS AOI is invalid.")
        temporary.replace(destination)
        LOG.info("Prepared HydroRIVERS AOI: %s (%s rivers)",destination.name,len(rivers))
        return destination
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        if own_session:
            session.close()

import csv
import os

GEONAMES_API_URL="https://secure.geonames.org/searchJSON"
GEONAMES_COLUMNS=[ "geonameid","name","asciiname","alternatenames","latitude","longitude",
    "feature_class","feature_code","country_code","cc2","admin1","admin2",
    "admin3","admin4","population","elevation","dem","timezone","modification_date"]

def _valid_geonames_file(path):
    try:
        if not path.is_file() or path.stat().st_size==0:
            return False
        with path.open("r",encoding="utf-8") as file:
            return len(file.readline().rstrip("\r\n").split("\t"))==19
    except (OSError,UnicodeError):
        return False

def _geonames_row(place):
    admin=place.get("adminCodes") or {}
    if not isinstance(admin,dict):
        admin={}
    name=place.get("toponymName") or place.get("name") or ""
    alternate=place.get("alternateNames") or []
    if isinstance(alternate,list):
        alternate=",".join(
            str(item.get("name","")) if isinstance(item,dict) else str(item)
            for item in alternate
        )
    timezone=place.get("timezone") or ""
    if isinstance(timezone,dict):
        timezone=timezone.get("timeZoneId","")
    return [
        place.get("geonameId",""),name,
        place.get("asciiName") or place.get("asciiname") or name,
        alternate,place.get("lat",""),place.get("lng",""),
        place.get("fcl","P"),place.get("fcode",""),
        place.get("countryCode",""),place.get("cc2",""),
        place.get("adminCode1") or admin.get("ADM1",""),
        place.get("adminCode2") or admin.get("ADM2",""),
        place.get("adminCode3") or admin.get("ADM3",""),
        place.get("adminCode4") or admin.get("ADM4",""),
        place.get("population") or 0,
        place.get("elevation") if place.get("elevation") is not None else "",
        place.get("srtm3") if place.get("srtm3") is not None else "",
        timezone,place.get("modificationDate","")]

def download_geonames(bounds,data_dir=DEFAULT_DATA_DIR,session=None,username=None):
    try:
        xmin,ymin,xmax,ymax=map(float,bounds)
    except (TypeError,ValueError) as exc:
        raise ValueError("bounds must be (xmin, ymin, xmax, ymax).") from exc

    if not (-180<=xmin<xmax<=180 and -90<=ymin<ymax<=90):
        raise ValueError("Invalid geographic bounds.")
    data_dir=Path(data_dir)
    cache_dir=data_dir/"geonames_aoi"
    key="_".join(f"{v:.6f}".replace("-","m").replace(".","p") for v in (xmin,ymin,xmax,ymax))
    destination=cache_dir/f"geonames_{key}.txt"
    if _valid_geonames_file(destination):
        LOG.info("Using cached GeoNames AOI: %s",destination.name)
        return destination
    username=(username or os.getenv("GEONAMES_USERNAME","ipmaFF")).strip()
    if not username:
        raise RuntimeError("Set the GEONAMES_USERNAME environment variable before downloading GeoNames.")

    cache_dir.mkdir(parents=True,exist_ok=True)
    destination.unlink(missing_ok=True)
    temporary=destination.with_name(destination.name+".part")
    own_session=session is None
    if own_session:
        session=requests.Session()
    places={}
    try:
        start=0
        while True:
            params={
                "north":ymax,"south":ymin,"east":xmax,"west":xmin,
                "featureClass":"P","maxRows":1000,"startRow":start,
                "style":"FULL","username":username}
            with session.get(GEONAMES_API_URL,params=params,timeout=(15,90)) as response:
                response.raise_for_status()
                result=response.json()
            if "status" in result:
                raise RuntimeError(f"GeoNames API error: {result['status']}")
            page=result.get("geonames") or []
            total=int(result.get("totalResultsCount",len(page)) or 0)
            if total>6000:
                raise ValueError(
                    f"Area returned {total} places, exceeding the free API pagination limit. "
                    "The area must be divided into smaller queries.")

            for place in page:
                try:
                    lat=float(place["lat"])
                    lon=float(place["lng"])
                except (KeyError,TypeError,ValueError):
                    continue
                if xmin<=lon<=xmax and ymin<=lat<=ymax:
                    places[str(place.get("geonameId",f"{lat}_{lon}_{place.get('name','')}"))]=place

            if not page:
                break
            start+=len(page)
            if start>=total or len(page)<1000:
                break
            if start>5000:
                raise ValueError("GeoNames free API pagination limit reached.")

        with temporary.open("w",encoding="utf-8",newline="") as file:
            writer=csv.writer(file,delimiter="\t",lineterminator="\n")
            if places:
                for place in places.values():
                    writer.writerow(_geonames_row(place))
            else:
                writer.writerow([""]*19)

        if not _valid_geonames_file(temporary):
            raise ValueError("Downloaded GeoNames data is invalid.")

        temporary.replace(destination)
        LOG.info("Prepared GeoNames AOI: %s (%s places)",destination.name,len(places))
        return destination

    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        if own_session:
            session.close()
            
from datetime import date, datetime, timedelta

CDSE_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
SENTINELHUB_PROCESS_URL = "https://sh.dataspace.copernicus.eu/process/v1"
BURNED_AREA_MONTHLY_COLLECTION = "b8b617c6-182f-427e-a86c-23fc36ac6098"
BURNED_AREA_EVALSCRIPT = """//VERSION=3
function setup(){return {input:[{bands:["DOB"]}],output:{bands:1,sampleType:"INT16"}}}
function evaluatePixel(s){return [s.DOB]}
"""
def _get_cdse_credentials():
    import getpass
    cached=getattr(_get_cdse_credentials,"_cache",None)
    if cached:
        return cached
    
    path=PROJECT_ROOT/"cdse_credentials.txt"

    if path.is_file():
        answer=input("Existing CDSE credentials found. Keep them? (y/n): ").strip().lower()
        if answer in ("y","yes"):
            credentials={}
            for line in path.read_text(encoding="utf-8").splitlines():
                key,sep,value=line.partition("=")
                if sep:
                    credentials[key.strip()]=value.strip()
            client_id=credentials.get("client_id")
            client_secret=credentials.get("client_secret")
            if client_id and client_secret:
                _get_cdse_credentials._cache=(client_id,client_secret)
                return _get_cdse_credentials._cache
            print("Credentials file is incomplete. Please enter new credentials.")

    client_id=input("CDSE Client ID: ").strip()
    client_secret=getpass.getpass("CDSE Client Secret: ").strip()

    if not client_id or not client_secret:
        raise RuntimeError("CDSE credentials were not provided.")

    temporary=path.with_name(path.name+".tmp")
    temporary.write_text(
        f"client_id={client_id}\nclient_secret={client_secret}\n",
        encoding="utf-8"
    )
    temporary.replace(path)

    _get_cdse_credentials._cache=(client_id,client_secret)
    return _get_cdse_credentials._cache

def _valid_burned_area_tiff(path, width, height):
    try:
        with rasterio.open(path) as src:
            return src.count == 1 and src.width == width and src.height == height
    except (OSError, rasterio.errors.RasterioError, ValueError):
        return False

def download_burned_area_aoi(bounds,data_dir=DEFAULT_DATA_DIR,years=range(2021, 2026),client_id=None,client_secret=None,
    session=None,width=None,height=None):
    """Download monthly Burnt Area DOB rasters only for bounds=(xmin,ymin,xmax,ymax)."""
    try:
        xmin, ymin, xmax, ymax = map(float, bounds)
    except (TypeError, ValueError) as exc:
        raise ValueError("bounds must be (xmin, ymin, xmax, ymax).") from exc
    if not (-180 <= xmin < xmax <= 180 and -90 <= ymin < ymax <= 90):
        raise ValueError("Invalid geographic bounds.")

    if not client_id or not client_secret:
        stored_id,stored_secret=_get_cdse_credentials()
        client_id=client_id or stored_id
        client_secret=client_secret or stored_secret

    years = sorted({int(year) for year in years})
    if not years or any(year < 2018 or year > datetime.now().year for year in years):
        raise ValueError("years must be between 2018 and the current year.")

    # Native monthly grid is approximately 1/336 degree.
    width = int(width or max(1, math.ceil((xmax - xmin) * 336)))
    height = int(height or max(1, math.ceil((ymax - ymin) * 336)))
    data_dir = Path(data_dir)
    key = "_".join(f"{v:.6f}".replace("-", "m").replace(".", "p") for v in (xmin, ymin, xmax, ymax))
    cache_dir = data_dir / "burned_area_aoi" / key
    cache_dir.mkdir(parents=True, exist_ok=True)

    own_session = session is None
    if own_session:
        session = requests.Session()

    def get_token():
        response = session.post(CDSE_TOKEN_URL,
            data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
            timeout=(15, 30))
        
        if response.status_code in (400,401):
            raise RuntimeError(
                "CDSE authentication failed. The Client ID or Client Secret may be incorrect. "
                "Please check your credentials and try again.")        
        response.raise_for_status()
        token = response.json().get("access_token")
        if not token:
            raise RuntimeError("CDSE authentication response did not contain an access token.")
        return token
    try:
        token = get_token()
        headers = {"Authorization": f"Bearer {token}"}
        paths = []
        total = len(years) * 12
        completed = 0
        for year in years:
            for month in range(1, 13):
                completed += 1
                destination = cache_dir / f"burned_area_{year}{month:02d}_{width}x{height}.tif"
                if _valid_burned_area_tiff(destination, width, height):
                    paths.append(destination)
                    print(f"[Burned Area {completed}/{total}] Cache: {year}-{month:02d}")
                    continue
                month_start = date(year, month, 1)
                next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
                month_end = datetime.combine(next_month, datetime.min.time()) - timedelta(seconds=1)
                payload = {
                    "input": {
                        "bounds": {"bbox": [xmin, ymin, xmax, ymax]},
                        "data": [{
                            "type": f"byoc-{BURNED_AREA_MONTHLY_COLLECTION}",
                            "dataFilter": {"timeRange": {
                                "from": f"{month_start:%Y-%m-%d}T00:00:00Z",
                                "to": f"{month_end:%Y-%m-%dT%H:%M:%S}Z"}}}]
                    },
                    "output": {
                        "width": width,
                        "height": height,
                        "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]
                    },
                    "evalscript": BURNED_AREA_EVALSCRIPT
                }
                print(f"[Burned Area {completed}/{total}] Downloading {year}-{month:02d}...")
                response = session.post(SENTINELHUB_PROCESS_URL, headers=headers, json=payload, timeout=(15, 90))
                if response.status_code == 401:
                    token = get_token()
                    headers = {"Authorization": f"Bearer {token}"}
                    response = session.post(SENTINELHUB_PROCESS_URL, headers=headers, json=payload, timeout=(15, 90))
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").lower()
                if "tiff" not in content_type:
                    raise RuntimeError(f"Expected a TIFF for {year}-{month:02d}; received {content_type}: {response.text[:300]}")

                temporary = destination.with_name(destination.stem + ".part.tif")
                try:
                    temporary.write_bytes(response.content)
                    if not _valid_burned_area_tiff(temporary, width, height):
                        raise ValueError(f"Invalid Burnt Area TIFF for {year}-{month:02d}.")
                    temporary.replace(destination)
                finally:
                    temporary.unlink(missing_ok=True)

                paths.append(destination)

        print(f"Burned Area download completed: {len(paths)} monthly rasters.")
        return paths
    finally:
        if own_session:
            session.close()