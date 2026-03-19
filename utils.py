from pyproj import Transformer
from shapely.ops import transform
import shapely.geometry
from pathlib import Path
import geopandas as gpd


def reproject_geom(src_geom, dst_crs, src_crs="EPSG:4326"):
    transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
    return transform(transformer.transform, src_geom)


def get_geom_from_geojson(file: Path, src_crs: int | str = 4326, to_crs: int | str = 3416) -> shapely.geometry.Polygon:
    data = gpd.read_file(file)
    geom = data.geometry.values[0]
    return reproject_geom(geom, dst_crs=to_crs, src_crs=src_crs)
