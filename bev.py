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
from utils import reproject_geom, get_geom_from_geojson


def determine_trgt_crs(gdf: gpd.GeoDataFrame, geom: shapely.geometry.Polygon) -> Tuple[gpd.GeoDataFrame, str, bool]:
    # select either 25832 or 25833 as trgt crs based on which has the largest proportional area (less effort in reproj)
    if gdf['src_crs'].nunique() >= 2:
        # calculate area
        gdf['intersection'] = gdf.intersection(geom)
        gdf['area'] = gdf['intersection'].area

        # agGregate and build sum, reuturn maximal index value as str epsg
        grouped = gdf.groupby('src_crs')
        group = grouped.agg(area=('area', 'sum'))
        trgt_crs, other_crs = group.idxmax().values[0], group.idxmin().values[0]

        # remove duplicate overlays of intersected geometries and keep those which are not trgt_crs
        trgt_union, other_gdf = grouped.get_group(trgt_crs).union_all(), grouped.get_group(other_crs)
        for row_index, row in other_gdf.iterrows():
            is_covered = trgt_union.covers(row['intersection'])
            if is_covered:
                gdf.drop(index=row_index, inplace=True)

        # check again if overlapping different crs rows have been removed in the overlap
        if gdf['src_crs'].nunique() >= 2:
            return gdf, trgt_crs, False
        else:
            return gdf, trgt_crs, True
    else:
        return gdf, gdf['src_crs'].iloc[0], True


def raster_logic(url: str, bounds_poly: shapely.geometry.Polygon, raster_crs: str,
                 trgt_crs: str) -> rio.MemoryFile | rio.DatasetReader:
    if raster_crs == trgt_crs:
        return rio.open(url, mode='r')

    else:
        # reproject bounds to get smaller field in full image, reproject to local raster crs
        trafo_bounds = reproject_geom(bounds_poly, raster_crs, src_crs=3416)

        with rio.open(url) as src:
            window = windows.from_bounds(*trafo_bounds.bounds, transform=src.transform)
            data = src.read(window=window, boundless=True)
            transform = windows.transform(window, transform=src.transform)

            # reproject to (majority) trgt_crs
            reproj_data, reproj_transform = warp.reproject(
                source=data,
                src_transform=transform,
                src_crs=src.crs,
                dst_crs=trgt_crs,
                resampling=warp.Resampling.nearest
            )

            profile = src.profile.copy()
            profile.update({'transform': reproj_transform,
                            'height': reproj_data.shape[1],
                            'width': reproj_data.shape[2],
                            'crs': trgt_crs})

            memfile = io.MemoryFile()
            with memfile.open(**profile) as dst:
                dst.write(reproj_data)
            return memfile.open()


def merge_data(gdf: gpd.GeoDataFrame,
               bounds_poly: shapely.geometry.Polygon,
               trgt_crs: int | str,
               single_crs: bool,
               output_path: Path,
               compression_options: Dict | None = None) -> None:
    if isinstance(trgt_crs, int):
        trgt_crs = f'EPSG:{trgt_crs}'

    if compression_options is None:
        compression_options = {"tiled": True,
                               "blockxsize": 512,
                               "blockysize": 512,
                               "compress": "jpeg",
                               "jpeg_quality": 85,
                               "interleave": "pixel"}

    print(f'downlaoding and merging data from {len(gdf)} tiles')
    if not single_crs:
        # complicated approach as different crs samples are used
        src_url = [raster_logic(url=row['url'],
                                bounds_poly=bounds_poly,
                                raster_crs=row['src_crs'],
                                trgt_crs=trgt_crs) for _, row in gdf.iterrows()]

        output_trafo_bounds = reproject_geom(bounds_poly, trgt_crs, src_crs=3416)
        rio.merge.merge(sources=src_url,
                        bounds=output_trafo_bounds.bounds,
                        dst_path=output_path,
                        dst_kwds=compression_options)
    else:
        urls = [row['url'] for _, row in gdf.iterrows()]
        rio.merge.merge(sources=urls,
                        bounds=reproject_geom(bounds_poly, trgt_crs, src_crs=3416).bounds,
                        dst_path=output_path,
                        dst_kwds=compression_options)
    return None


start = time.time()
# in 3416
# sample_linz_four_boxes = shapely.geometry.box(470947, 487593, 475309, 491080)
# sample_border_crs33 = shapely.geometry.box(320010, 383643, 329011, 387684)
# sample_border_both_crs = shapely.geometry.box(266875, 324372, 324215, 350435)


# sampels = {'four_boxes': {'geometry': sample_linz_four_boxes},
#            'intersection_33_tirol': {'geometry': sample_border_crs33},
#            'intersection_both_crs_tirol': {'geometry': sample_border_both_crs},
#            'kamp': {'geometry': curr_sample}}
# sampels_gdf = gpd.GeoDataFrame(pd.DataFrame.from_dict(sampels, orient='index'), crs=3416)
# sampels_gdf.to_file('files/samples.gpkg', driver='GPKG')

AOI = get_geom_from_geojson(Path('input/bbox_thernberg.geojson'), to_crs=3416, src_crs=4326)
gdf = gpd.read_file('files/oek_50_reference.gpkg')
outfile = Path('images/thernberg.tif')

req_imgs = gdf[gdf.intersects(AOI)]
req_imgs, trgt_crs, single_crs_req = determine_trgt_crs(req_imgs, geom=AOI)

# reproject
merge_data(req_imgs,
           bounds_poly=AOI,
           trgt_crs=trgt_crs,
           single_crs=single_crs_req,
           output_path=outfile)

stop = time.time()
print(stop - start)

# process:
# get bbox for map
# intersect with gdf and retrieve img data (img, transform, bounds)
# merge together
# seperate onto pdf
# add metadata
