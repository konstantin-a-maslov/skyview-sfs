import jax.numpy as jnp
import svsfs.reflectance_models


def forward(
    params,
    albedo, 
    z_prior,
    sun_vector, # surface -> sun
    sensor_vector, # surface -> sensor
    dx, dy,
):
    delta_z, g, b, d = params

    z = z_prior + delta_z
    n = normals(z, dx, dy)

    cos_i = jnp.sum(n * sun_vector, axis=-1)
    cos_e = jnp.sum(n * sensor_vector, axis=-1)
    cos_alpha = jnp.sum(sun_vector * sensor_vector, axis=-1)
    alpha = jnp.arccos(jnp.clip(cos_alpha, -1.0, 1.0))

    ### TODO!
    sun_factor = 1.0
    sky_factor = 0.0
    ###

    r = svsfs.reflectance_models.lunar_lambert(alpha, cos_i, cos_e)
    illumination = sun_factor * r + d * sky_factor
    image = g * albedo * illumination + b

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
