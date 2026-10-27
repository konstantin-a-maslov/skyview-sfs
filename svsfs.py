import argparse
import pathlib


def main():
    args = resolve_cli_args()

    caller = {
        "reconstruct_dem": reconstruct_dem,
        "forward": forward,
    }[args.command]

    caller(args)


def reconstruct_dem(args):
    raise NotImplementedError()


def forward(args):
    import io_ops
    import utils
    import model.forward

    z = io_ops.read_scene(args.input)
    dx, dy = (abs(_) for _ in z.rio.resolution())

    albedo = args.albedo
    if isinstance(albedo, pathlib.Path):
        raise NotImplementedError("Spatially varying albedo is not yet supported")

    z.attrs.update(dict(
        sun_azimuth=args.sun_azimuth, 
        sensor_azimuth=args.sensor_azimuth, 
    ))
    z = io_ops.convert_azimuths_to_image_space(z)
    sun_vector = utils.azel_to_vector(z.attrs["sun_azimuth_img"], args.sun_elevation)
    sensor_vector = utils.azel_to_vector(z.attrs["sensor_azimuth_img"], args.sensor_elevation)

    return_aux = bool(args.r or args.sun_factor or args.sky_factor)
    params = z.data, args.g, args.b, args.d, args.kappa

    image = model.forward.forward(
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
    if return_aux:
        image, aux = image

    import matplotlib.pyplot as plt
    plt.imshow(image, cmap="gray")
    plt.tight_layout()
    plt.show()

    


def resolve_cli_args():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    # reconstruct_dem
    reconstruct_dem = commands.add_parser("reconstruct_dem")

    # forward
    forward = commands.add_parser("forward")
    forward.add_argument("--input", type=pathlib.Path, required=True, help="Input DEM raster (GDAL-supported)")
    forward.add_argument("--output", type=pathlib.Path, required=True, help="Output I/F raster (GDAL-supported)")
    forward.add_argument("--g", type=float, default=1.0, help="Image gain factor")
    forward.add_argument("--b", type=float, default=0.0, help="Image bias factor")
    forward.add_argument("--d", type=float, default=0.5, help="Diffuse sky gain factor")
    forward.add_argument("--kappa", type=float, default=3.0, help="Diffuse sky anisotropicity parameter")
    forward.add_argument("--albedo", type=path_or_float, default=0.35, help="Albedo (GDAL-supported raster or float)")
    forward.add_argument("--sun_azimuth", type=float, required=True, help="Sun azimuth")
    forward.add_argument("--sun_elevation", type=float, required=True, help="Sun elevation")
    forward.add_argument("--sensor_azimuth", type=float, required=True, help="Sensor azimuth")
    forward.add_argument("--sensor_elevation", type=float, required=True, help="Sensor elevation")
    forward.add_argument("--no_cast_shadows", action="store_true", default=False, help="Turn off shadow casting")
    forward.add_argument("--no_diffuse_sky", action="store_true", default=False, help="Turn off diffuse sky illumination")
    forward.add_argument("--diffuse_sky_n_azimuth", type=int, default=32, help="Number of azimuth directions for diffuse sky illumination calculation")
    forward.add_argument("--diffuse_sky_n_elevation", type=int, default=32, help="Number of elevation directions for diffuse sky illumination calculation")
    forward.add_argument("--diffuse_sky_azimuth_batch_size", type=int, default=1, help="Batch size for traversing azimuth directions for diffuse sky illumination calculation")
    forward.add_argument("--horizon_softness", type=float, default=0.0025, help="Softness parameter of horizon operator")
    forward.add_argument("--r", type=pathlib.Path, help="Output raw terrain-unaware illumination (GDAL-supported)")
    forward.add_argument("--sun_factor", type=pathlib.Path, help="Output cast shadows (GDAL-supported)")
    forward.add_argument("--sky_factor", type=pathlib.Path, help="Output diffuse sky contribution before its gain (GDAL-supported)")

    args = parser.parse_args()
    return args


def path_or_float(value):
    try:
        return float(value)
    except ValueError:
        return pathlib.Path(value)


if __name__ == "__main__":
    main()
