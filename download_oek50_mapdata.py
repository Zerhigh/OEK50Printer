import os
import time
import rasterio as rio
import geopandas as gpd
import shapely.geometry

from rasterio import windows, warp, io, merge
from typing import Tuple, Any, Dict, List
from pathlib import Path

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


def raster_logic(url: str,
                 bounds_poly: shapely.geometry.Polygon,
                 raster_crs: str,
                 trgt_crs: str) -> rio.MemoryFile | rio.DatasetReader:
    # if already in correct crs just return it opened for rio.merge()
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
               compression_options: Dict | None = None,
               verbose=False) -> None:
    if isinstance(trgt_crs, int):
        trgt_crs = f'EPSG:{trgt_crs}'

    if compression_options is None:
        compression_options = {"tiled": True,
                               "blockxsize": 512,
                               "blockysize": 512,
                               "compress": "jpeg",
                               "jpeg_quality": 85,
                               "interleave": "pixel"}

    if verbose:
        print(f'    Downloading and merging data from {len(gdf)} tiles')
        print('    This might take some time, depending on your internet speed and AOI area.')
        print('    Expect one minute per 400 million square meter.')

    if not single_crs:
        # complicated approach as different crs samples are used
        if verbose:
            print(f'    Tiles cover multiple UTM strips, data will be merged into {trgt_crs}')

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


if __name__ == '__main__':
    start = time.time()
    AOI_file = Path('inputs/bbox_thernberg.geojson')
    oek50_ref_data = Path('files/oek_50_reference.gpkg')
    outfile = Path('images/thernberg.tif')

    assert AOI_file.exists()
    assert oek50_ref_data.exists()
    if not outfile.parent.exists():
        os.mkdir(outfile.parent)

    print(f'Downloading map data for the AOI provided in: {AOI_file}')

    AOI = get_geom_from_geojson(AOI_file, to_crs=3416, src_crs=4326)
    gdf = gpd.read_file(oek50_ref_data)

    req_imgs = gdf[gdf.intersects(AOI)]
    req_imgs, trgt_crs, single_crs_req = determine_trgt_crs(req_imgs, geom=AOI)

    # reproject
    merge_data(req_imgs,
               bounds_poly=AOI,
               trgt_crs=trgt_crs,
               single_crs=single_crs_req,
               output_path=outfile,
               verbose=True)

    stop = time.time()
    print(f'Downloading image data took: {round(stop - start, 2)}s')
