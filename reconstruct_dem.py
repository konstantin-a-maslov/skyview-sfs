import io_ops
import utils
import numpy as np
import geopandas
import rasterio
from tqdm import tqdm


def run(args):
    scenes = []
    for path in args.inputs:
        scenes.append(io_ops.read_scene(path))
    z_prior = io_ops.read_scene(args.z_prior)

    bbox = geopandas.read_file(args.bbox)
    grid = io_ops.create_grid(bbox, args.res)
    grid, padding = utils.pad_to_fit_tiles(grid, args.tile_size)

    scenes = [_.rio.reproject_match(grid, resampling=rasterio.enums.Resampling.lanczos) for _ in scenes]
    scenes = [io_ops.convert_azimuths_to_image_space(_) for _ in scenes]
    z_prior = z_prior.rio.reproject_match(grid, resampling=rasterio.enums.Resampling.bilinear)

    (h, w), tile_size = grid.shape, args.tile_size
    n_steps_y, n_steps_x = 2 * h // tile_size - 1, 2 * w // tile_size - 1

    with tqdm(total=n_steps_y * n_steps_x, desc="") as pbar:
        for row in range(0, h - tile_size + 1, tile_size // 2):
            for col in range(0, w - tile_size + 1, tile_size // 2):
                slice_y, slice_x = slice(row, row + tile_size), slice(col, col + tile_size)
                elevation, albedo = reconstruction_loop(scenes, z_prior, slice_y, slice_x, args, pbar)
                pbar.update(1)

    ####
    # import matplotlib.pyplot as plt

    # nrows, ncols = 1, 1 + len(scenes)

    # _, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(ncols * 7, 7))

    # z_prior.plot.imshow(ax=axes[0], robust=True, cmap="terrain")
    # for ax, scene in zip(axes[1:], scenes):
    #     print(scene.attrs)
    #     scene.plot.imshow(ax=ax, robust=True, cmap="gray")

    # plt.tight_layout()
    # plt.show()
    ####


def reconstruction_loop(scenes, z_prior, slice_y, slice_x, args, pbar=None):
    scenes = [_[slice_y, slice_x] for _ in scenes]
    z_prior = z_prior[slice_y, slice_x]

    iter, diff = 0, np.inf
    while True:
        step()
        iter += 1

        if pbar:
            pbar.set_description(f"iteration {iter}, some stats here")

        if args.max_iter and iter >= args.max_iter:
            break

        if diff < args.tolerance:
            break

    return None, None


def step():
    pass
