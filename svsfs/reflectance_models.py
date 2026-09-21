import jax.numpy as jnp


def hapke(alpha, cos_i, cos_e):
    raise NotImplementedError()


def lambert(alpha, cos_i, cos_e):
    r = cos_i

    valid = (cos_i > 0.0) & (cos_e > 0.0)
    return jnp.where(valid, r, 0.0)


def lunar_lambert(alpha, cos_i, cos_e, eps=1e-6):
    alpha = jnp.degrees(alpha)

    a, b, c = -0.019, 2.42e-4, -1.46e-6
    l_alpha = 1.0 + a * alpha + b * alpha**2 + c * alpha**3

    denom = jnp.maximum(cos_i + cos_e, eps)
    r = l_alpha * 2 * cos_i / denom + (1 - l_alpha) * cos_i

    valid = (cos_i > 0.0) & (cos_e > 0.0)
    return jnp.where(valid, r, 0.0)
