from pyproj import Transformer
from shapely.ops import transform
import time

import rasterio as rio
import rasterio.merge
import shapely.geometry
from rasterio import windows, warp, io
from typing import Tuple, Any, Dict, List
import numpy as np
from pathlib import Path
import geopandas as gpd
import pandas as pd


def reproject_geom(src_geom, dst_crs, src_crs="EPSG:4326"):
    transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
    return transform(transformer.transform, src_geom)


def get_geom_from_geojson(file: Path, src_crs: int | str = 4326, to_crs: int | str = 3416) -> shapely.geometry.Polygon:
    data = gpd.read_file(file)
    geom = data.geometry.values[0]
    return reproject_geom(geom, dst_crs=to_crs, src_crs=src_crs)


def write_img_data(data: np.ndarray, profile: Dict, outpath: Path) -> None:
    with rio.open(outpath, 'w', **profile) as dst:
        dst.write(data)
    return None


def get_img_data(url: str, bbox: List[float]) -> Tuple[np.ndarray, Any]:
    with rio.open(url) as src:
        window = windows.from_bounds(*bbox, transform=src.transform)
        data = src.read(window=window, boundless=True)
        trafo = windows.transform(window, transform=src.transform)

        profile = src.profile.copy()
        profile.update({'transform': trafo,
                        'height': data.shape[1],
                        'width': data.shape[2]})

    return data, profile
