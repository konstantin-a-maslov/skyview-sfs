import jax.numpy as jnp


def azel_to_vector(azimuth, elevation, degrees=True):
    if degrees:
        azimuth = jnp.deg2rad(azimuth)
        elevation = jnp.deg2rad(elevation)

    return jnp.stack([
        jnp.cos(elevation) * jnp.sin(azimuth),
        jnp.cos(elevation) * jnp.cos(azimuth),
        jnp.sin(elevation),
    ], axis=-1)
