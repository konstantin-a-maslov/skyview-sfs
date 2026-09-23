import jax.numpy as jnp
import jax.scipy.ndimage
import svsfs.reflectance_models
import math


def forward(
    params,
    albedo, 
    z_prior,
    sun_vector, # surface -> sun
    sensor_vector, # surface -> sensor
    dx, dy,
    cast_shadows=True,
    diffuse_sky=True,
    diffuse_sky_n_azimuth=32, 
    diffuse_sky_n_elevation=16,
    horizon_softness=1e-2, # in radians
    return_aux=False,
):
    delta_z, g, b, d = params
    sun_factor, sky_factor = jnp.ones_like(delta_z), jnp.zeros_like(delta_z)

    z = z_prior + delta_z
    n = normals(z, dx, dy)

    cos_i = jnp.sum(n * sun_vector, axis=-1)
    cos_e = jnp.sum(n * sensor_vector, axis=-1)
    cos_alpha = jnp.sum(sun_vector * sensor_vector, axis=-1)
    alpha = jnp.arccos(jnp.clip(cos_alpha, -1.0, 1.0))
    if cast_shadows:
        sun_factor = horizon_operator(z, sun_vector, dx, dy, softness=horizon_softness)
    r = svsfs.reflectance_models.lunar_lambert(alpha, cos_i, cos_e)

    if diffuse_sky:
        sky_dirs = hemisphere_directions(
            n_azimuth=diffuse_sky_n_azimuth, 
            n_elevation=diffuse_sky_n_elevation,
        )
        def sky_factor_step(total, dir_vector):
            cos_i = jnp.sum(n * dir_vector, axis=-1)
            cos_alpha = jnp.sum(dir_vector * sensor_vector, axis=-1)
            alpha = jnp.arccos(jnp.clip(cos_alpha, -1.0, 1.0))
            visibility = horizon_operator(z, dir_vector, dx, dy, softness=horizon_softness)
            r = svsfs.reflectance_models.lunar_lambert(alpha, cos_i, cos_e)
            total += visibility * r
            return total, None
        sky_factor = jnp.zeros_like(z)
        sky_factor, _ = jax.lax.scan(sky_factor_step, sky_factor, sky_dirs) # consider batchifying it here
        sky_factor /= sky_dirs.shape[0]

    illumination = sun_factor * r + d * sky_factor
    image = g * albedo * illumination + b

    if return_aux:
        aux = {
            "r": r,
            "sun_factor": sun_factor,
            "sky_factor": sky_factor,
        }
        return image, aux

    return image


def normals(z, dx=1.0, dy=1.0):
    dz_dy, dz_dx = jnp.gradient(z, dy, dx)

    n = jnp.stack([
        -dz_dx,
        dz_dy, # raster convention
        jnp.ones_like(z),
    ], axis=-1)
    n /= jnp.linalg.norm(n, axis=-1, keepdims=True)

    return n


def horizon_operator(
    z, 
    dir_vector,
    dx, dy, 
    sample_step_px=1.0,
    softness=1e-2,
    eps=1e-6,
):
    ny, nx = z.shape
    vx, vy, vz = dir_vector
    horizontal = jnp.hypot(vx, vy)

    horizontal_safe = jnp.maximum(horizontal, eps)
    ux = vx / horizontal_safe
    uy = vy / horizontal_safe
    tan_elevation = vz / horizontal_safe
    cos2 = 1.0 / (1.0 + tan_elevation**2) # to convert softness to slope space

    pixels_per_metre = jnp.maximum(jnp.abs(ux) / dx, jnp.abs(uy) / dy)
    ds = sample_step_px / jnp.maximum(pixels_per_metre, eps)
    drow, dcol = -uy * ds / dy, ux * ds / dx

    row0 = jnp.arange(ny, dtype=z.dtype)[:, None]
    col0 = jnp.arange(nx, dtype=z.dtype)[None, :]
    n_steps = math.ceil(max(ny - 1, nx - 1) / sample_step_px) + 1
    ks = jnp.arange(1, n_steps + 1, dtype=z.dtype)

    def step(excess, k):
        rr, cc = row0 + k * drow, col0 + k * dcol
        valid = (rr >= 0.0) & (rr <= ny - 1) & (cc >= 0.0) & (cc <= nx - 1)
        z_sample = jax.scipy.ndimage.map_coordinates(
            z, [rr, cc], order=1, mode="nearest",
        )
        e = (z_sample - z) / (k * ds) - tan_elevation
        excess = jnp.where(valid, jnp.maximum(excess, e), excess)
        return excess, None

    excess0 = jnp.full_like(z, -jnp.inf)
    excess, _ = jax.lax.scan(step, excess0, ks)
    visibility = jax.nn.sigmoid(-excess * cos2 / softness)

    visibility = jnp.where(horizontal < eps, jnp.ones_like(z), visibility)
    visibility = jnp.where(vz > 0.0, visibility, jnp.zeros_like(z))

    return visibility


def hemisphere_directions(n_azimuth=32, n_elevation=16):
    az = (jnp.arange(n_azimuth) + 0.5) * 2.0 * jnp.pi / n_azimuth
    sin_el = (jnp.arange(n_elevation) + 0.5) / n_elevation
    az, sin_el = jnp.meshgrid(az, sin_el, indexing="xy")
    cos_el = jnp.sqrt(1.0 - sin_el**2)

    dirs = jnp.stack([
        cos_el * jnp.sin(az), 
        cos_el * jnp.cos(az),
        sin_el,
    ], axis=-1)

    return dirs.reshape(-1, 3)
