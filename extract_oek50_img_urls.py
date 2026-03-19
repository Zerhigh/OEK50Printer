import json
import rasterio as rio
from shapely.geometry import box
from tqdm import tqdm
from typing import Dict
from pathlib import Path
import geopandas as gpd
import pandas as pd

from utils import reproject_geom


def extract_urls(data: Dict) -> Dict:
    urls = {}
    for img_obj in data['hits']['hits']:
        links = img_obj['_source']['link']
        for link in links:
            if link['idx'] == 4:
                # irregular naming convention but id is always last
                single_img_id = link['nameObject']['default'].split(' ')[-1]
                urls[single_img_id] = {'url': link['urlObject']['default']}
    return urls


if __name__ == '__main__':
    # open and extract relevant urls
    fn = Path('files/BEV_url_hits.json')
    out_fn = 'files/oek_50_reference.gpkg'
    assert fn.exists()

    print('Extracting image urls from scraped BEV website call')
    with open(fn, 'r') as file:
        json_data = json.load(file)
        img_urls = extract_urls(json_data)

    # get bbox of each entry and create geopandas
    for img_id, values in tqdm(img_urls.items()):
        with rio.open(values['url'], 'r') as src:
            geo = box(*src.bounds)
            img_urls[img_id].update({'crs': 3416,
                                     'src_crs': src.crs,
                                     'geometry': reproject_geom(src_geom=box(*src.bounds),
                                                                dst_crs=3416,
                                                                src_crs=src.crs)})

    gdf = gpd.GeoDataFrame(pd.DataFrame.from_dict(img_urls, orient='index'), crs=3416)
    gdf.to_file(out_fn, 'GPKG')
