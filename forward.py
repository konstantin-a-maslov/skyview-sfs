import model.forward
import io_ops
import rasterio
import utils
import pathlib


def run(args):
    z = io_ops.read_scene(args.input)
    dx, dy = (abs(_) for _ in z.rio.resolution())

    albedo = args.albedo
    if isinstance(albedo, pathlib.Path):
        albedo = io_ops.read_scene(albedo)
        albedo = albedo.rio.reproject_match(z, resampling=rasterio.enums.Resampling.bilinear)
        albedo = albedo.data

    z.attrs.update(dict(sun_azimuth=args.sun_azimuth, sensor_azimuth=args.sensor_azimuth))
    z = io_ops.convert_azimuths_to_image_space(z)
    sun_vector = utils.azel_to_vector(z.attrs["sun_azimuth_img"], args.sun_elevation)
    sensor_vector = utils.azel_to_vector(z.attrs["sensor_azimuth_img"], args.sensor_elevation)

    return_aux = bool(args.r or args.sun_factor or args.sky_factor)
    params = z.data, args.g, args.b, args.d, args.kappa
    kwargs = dict(
        params=params,
        albedo=albedo, 
        z_prior=0.0,
        sun_vector=sun_vector, 
        sensor_vector=sensor_vector, 
        dx=dx, 
        dy=dy,
        cast_shadows=not args.no_cast_shadows,
        diffuse_sky=not args.no_diffuse_sky,
        diffuse_sky_n_azimuth=args.diffuse_sky_n_azimuth, 
        diffuse_sky_n_elevation=args.diffuse_sky_n_elevation, 
        diffuse_sky_azimuth_batch_size=args.diffuse_sky_azimuth_batch_size,
        horizon_softness=args.horizon_softness,
        return_aux=return_aux,
    )

    if args.tile_size is None:
        image = model.forward.forward(**kwargs)
        if return_aux:
            image, aux = image

    else:
        raise NotImplementedError("Tiling is not yet implemented for forward")

    io_ops.write_array_with_georef(image, z, args.output, name="I/F (model)")
    for key in ["r", "sun_factor", "sky_factor"]:
        if (arg_val := getattr(args, key, None)):
            io_ops.write_array_with_georef(aux[key], z, arg_val, name=key)
