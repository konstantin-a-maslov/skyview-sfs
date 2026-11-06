import jax.numpy as jnp
import numpy as np


def azel_to_vector(azimuth, elevation, degrees=True):
    if degrees:
        azimuth = jnp.deg2rad(azimuth)
        elevation = jnp.deg2rad(elevation)

    return jnp.stack([
        jnp.cos(elevation) * jnp.sin(azimuth),
        jnp.cos(elevation) * jnp.cos(azimuth),
        jnp.sin(elevation),
    ], axis=-1)


def pad_to_fit_tiles(grid, tile_size, min_border=0):
    h, w = grid.rio.shape

    extra_x = (-(w + 2 * min_border)) % tile_size
    extra_y = (-(h + 2 * min_border)) % tile_size

    pad_left = min_border + extra_x // 2
    pad_right = min_border + extra_x - extra_x // 2
    pad_top = min_border + extra_y // 2
    pad_bottom = min_border + extra_y - extra_y // 2

    res_x, res_y = grid.rio.resolution()
    left, bottom, right, top = grid.rio.bounds()

    padded = grid.rio.pad_box(
        minx=left - pad_left * res_x,
        miny=bottom - pad_bottom * abs(res_y),
        maxx=right + pad_right * res_x,
        maxy=top + pad_top * abs(res_y),
        constant_values=np.nan,
    )

    padding = {
        "left": pad_left,
        "right": pad_right,
        "top": pad_top,
        "bottom": pad_bottom,
    }

    return padded, padding
