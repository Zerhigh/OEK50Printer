import json
import rasterio as rio
from shapely.geometry import box
from tqdm import tqdm
import geopandas as gpd
import pandas as pd

from utils import reproject_geom


# open and extract relevant urls
with open('files/BEV_url_hits.json', 'r') as file:
    data = json.load(file)
    img_urls = {}
    for img_obj in data['hits']['hits']:
        links = img_obj['_source']['link']
        for link in links:
            if link['idx'] == 4:
                # irregular naming convention but id is always last
                img_id = link['nameObject']['default'].split(' ')[-1]
                img_urls[img_id] = {'url': link['urlObject']['default']}


# get bbox of each entry and create geopandas
for img_id, values in tqdm(img_urls.items()):
    with rio.open(values['url'], 'r') as src:
        geo = box(*src.bounds)
        img_urls[img_id].update({'geometry': reproject_geom(src_geom=box(*src.bounds),
                                                            dst_crs=3416,
                                                            src_crs=src.crs),
                                 'crs': 3416,
                                 'src_crs': src.crs})


gdf = gpd.GeoDataFrame(pd.DataFrame.from_dict(img_urls, orient='index'), crs=3416)
gdf.to_file('files/oek_50_reference.gpkg', 'GPKG')

