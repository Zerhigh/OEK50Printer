import rasterio as rio
from rasterio import windows
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import matplotlib.pyplot as plt
import numpy as np
from typing import List, Tuple


def mm_to_pix(val: int | float):
    return math.floor(val * 11.81048581)


def create_scale_bar(trafo_px_in_m: float | int,
                     marks: List[int],
                     vertical_shape: float | int,
                     max_horizontal_shape: float | int) -> Tuple[np.ndarray, List[int]]:
    # max horizontal shape will be reduced baseD on marks
    assert sorted(marks) == marks
    assert int(np.ceil(marks[-1] / trafo_px_in_m)) <= max_horizontal_shape

    scale_bar = np.full(shape=(vertical_shape, int(np.ceil(marks[-1] / trafo_px_in_m)), 3),
                        fill_value=255,
                        dtype=np.uint8)

    horizontal_positions = [0]
    for i, mark in enumerate(marks):
        # determine up or down for chess structure,
        pos = bool(i % 2)
        vert_pos = slice(0, int(np.floor(vertical_shape / 2))) if pos else slice(int(np.floor(vertical_shape / 2)),
                                                                                 int(np.floor(vertical_shape)))

        # horizontal offset
        px_pos = int(np.floor(mark / trafo_px_in_m))
        scale_bar[vert_pos, horizontal_positions[-1]:px_pos, :] = 0
        horizontal_positions.append(px_pos)

    # add boundary
    scale_bar[0:5, :, :] = 0
    scale_bar[-5:, :, :] = 0
    scale_bar[:, 0:5, :] = 0
    scale_bar[:, -5:, :] = 0

    return scale_bar, horizontal_positions


def folding_lines(tile: np.ndarray,
                  add_i: bool,
                  add_j: bool,
                  folding_line_method: str,
                  available_page_width: int,
                  available_page_height: int,
                  height: int) -> np.ndarray:
    # until the end of the map section is reached, add the folding info
    if add_i:
        # if i != tiles_x - 1:
        # two small markers at the border
        if folding_line_method == 'minimal':
            width_border = slice(int(available_page_width), int(available_page_width) + 10)
            # left
            tile[0: 30, width_border, :] = 0
            tile[0: 30, width_border, 0] = 255

            # riht
            tile[-30:, width_border, :] = 0
            tile[-30:, width_border, 0] = 255

        elif folding_line_method == 'full':
            width_border = slice(int(available_page_width), int(available_page_width) + 5)
            tile[:, width_border, :] = 0
            tile[:, width_border, 0] = 255

    # if not the first row of tiles, add folding instruction to cover redundant scale bar
    if add_j:
        # if j != 0:
        # two small markers at the border
        if folding_line_method == 'minimal':
            height_border = slice(int(height - available_page_height),
                                  int(height - available_page_height) + 10)
            # up
            tile[height_border, 0: 30, :] = 0
            tile[height_border, 0: 30, 0] = 255

            # down
            tile[height_border, -30:, :] = 0
            tile[height_border, -30:, 0] = 255

        elif folding_line_method == 'full':
            height_border = slice(int(height - available_page_height),
                                  int(height - available_page_height) + 10)
            tile[height_border, :, :] = 0
            tile[height_border, :, 0] = 255

    return tile


def tile_img(fn: Path,
             out_folder: Path,
             to_file: str = 'pdf',
             print_margin: int = 8,  # in mm
             metainfo_margin: int = 5,  # in mm
             margin_unit: str = 'mm',
             scale_bar_marks: List[int] | None = None,
             add_folding_lines: bool = True,
             folding_line_method: str = 'minimal') -> None:

    assert to_file in ['pdf', 'tif']
    assert folding_line_method in ['minimal', 'full']

    page_width_px, page_height_px = 3508, 2480

    # remove metainfo_margin for tif files
    if to_file == 'tif':
        metainfo_margin = 0

    if margin_unit == 'mm':
        print_margin_px = mm_to_pix(print_margin)
        metainfo_margin_px = mm_to_pix(metainfo_margin)
    else:
        print('margin unit not viable')
        return None

    base_available_page_width = page_width_px - 2 * (print_margin_px + metainfo_margin_px)
    base_available_page_height = page_height_px - 2 * (print_margin_px + metainfo_margin_px)

    with (rio.open(fn, 'r') as src):
        # create empty image and add metainfo
        if to_file == 'pdf':
            # force override scale bars
            if not scale_bar_marks:
                scale_bar_marks = [250, 500, 1000, 2000, 3000, 4000, 5000]
                print(f'scale marks are created automatically: {scale_bar_marks}')

            blank_page = Image.new('RGB', (page_width_px, page_height_px), color=(255, 255, 255))

            # insert scalebar
            scalebar, horizontal_positions = create_scale_bar(trafo_px_in_m=src.transform.a,
                                                              marks=scale_bar_marks,
                                                              vertical_shape=metainfo_margin_px - 10,
                                                              max_horizontal_shape=base_available_page_width)

            margined_text = [(val+print_margin_px+2*metainfo_margin_px, print_margin_px+20) for val in horizontal_positions]
            scale_bar_texts = ['0m']
            for mark in scale_bar_marks:
                scale_bar_texts.append(f'{mark}m')
            #scale_bar_texts = [f'{mark}m' for mark in scale_bar_marks]
            draw = ImageDraw.Draw(blank_page)
            font = ImageFont.truetype("arial.ttf", 30)
            for (x, y), text in zip(margined_text, scale_bar_texts):
                draw.text((x, y), text, fill=(0, 0, 0), font=font)

            paste_box = (print_margin_px + 2 * metainfo_margin_px, print_margin_px + metainfo_margin_px)
            blank_page.paste(Image.fromarray(scalebar), paste_box)
        else:
            blank_page = None

        tiles_x = math.ceil(src.width / base_available_page_width)
        tiles_y = math.ceil(src.height / base_available_page_height)

        # fit images to fill out and add overlap
        max_width = tiles_x * base_available_page_width
        max_heigth = tiles_y * base_available_page_height

        unused_width_per_tile = (max_width - src.width) / (tiles_x - 1) if tiles_x > 1 else 0
        unused_height_per_tile = (max_heigth - src.height) / (tiles_y - 1)if tiles_y > 1 else 0

        available_page_width = base_available_page_width - unused_width_per_tile
        available_page_height = base_available_page_height - unused_height_per_tile

        for i in range(tiles_x):
            for j in range(tiles_y):
                col_off = i * available_page_width
                row_off = j * available_page_height
                width = base_available_page_width
                height = base_available_page_height

                window = windows.Window(col_off, row_off, width, height)
                tile = src.read(window=window)
                out_fn = out_folder / f'{fn.stem}_{j}_{i}.{to_file}'

                if to_file == 'tif':
                    transform = windows.transform(window, transform=src.transform)

                    new_profile = src.profile.copy()
                    new_profile.update({'transform': transform,
                                        'height': tile.shape[1],
                                        'width': tile.shape[2],
                                        })

                    with rio.open(out_fn, 'w', **new_profile) as dst:
                        dst.write(tile)

                elif to_file == 'pdf':
                    ttile = tile.transpose(1, 2, 0)

                    # adding folding line instructions
                    if add_folding_lines:
                        ttile = folding_lines(tile=ttile,
                                              add_i=i != tiles_x - 1,
                                              add_j=j != 0,
                                              folding_line_method=folding_line_method,
                                              available_page_width=available_page_width,
                                              available_page_height=available_page_height,
                                              height=height)

                    tiled_img = Image.fromarray(ttile)
                    page = blank_page.copy()
                    paste_box = (print_margin_px + metainfo_margin_px, print_margin_px + 2 * metainfo_margin_px)
                    page.paste(tiled_img, paste_box)

                    # add tile numbering
                    draw = ImageDraw.Draw(page)
                    font = ImageFont.truetype("arial.ttf", 30)
                    draw.text((print_margin_px + metainfo_margin_px, print_margin_px + metainfo_margin_px),
                              f'{j}_{i}', fill=(0, 0, 0), font=font)

                    page.save(out_fn)

    return None


tile_img(Path("images/kamp_2.tif"),
         out_folder=Path('pdfs'),
         to_file='pdf',
         scale_bar_marks=[250, 500, 1000, 2000, 3000, 4000, 5000]
         )
