import jax.numpy as jnp


def hapke(alpha, cos_i, cos_e, eps=1e-6):
    raise NotImplementedError()


def lambert(alpha, cos_i, cos_e):
    r = cos_i
    r = mask_invalid(r, cos_i, cos_e)
    return r


def lunar_lambert(alpha, cos_i, cos_e, a=-0.019, b=2.42e-4, c=-1.46e-6, eps=1e-6):
    alpha = jnp.degrees(alpha)
    l_alpha = 1.0 + a * alpha + b * alpha**2 + c * alpha**3

    denom = jnp.maximum(cos_i + cos_e, eps)
    r = l_alpha * 2 * cos_i / denom + (1 - l_alpha) * cos_i

    r = mask_invalid(r, cos_i, cos_e)
    return r


def mask_invalid(r, cos_i, cos_e):
    valid = (cos_i > 0.0) & (cos_e > 0.0)
    r = jnp.where(valid, r, 0.0)
    valid = jnp.isfinite(cos_i) & jnp.isfinite(cos_e)
    r = jnp.where(valid, r, jnp.nan)
    return r
