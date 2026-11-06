import argparse
import warnings
import pathlib


def main():
    args = resolve_cli_args()

    caller = {
        "reconstruct-dem": reconstruct_dem,
        "forward": forward,
    }[args.command]

    caller(args)


def reconstruct_dem(args):
    if args.max_iter is None:
        warnings.warn(
            "No --max-iter specified. The algorithm may run indefinitely if it fails to converge.",
            RuntimeWarning,
            stacklevel=1
        )

    import reconstruct_dem
    reconstruct_dem.run(args)


def forward(args):
    import forward
    forward.run(args)


def resolve_cli_args():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    # reconstruct_dem
    reconstruct_dem = commands.add_parser("reconstruct-dem")
    reconstruct_dem.add_argument("--inputs", nargs="+", type=pathlib.Path, required=True, help="Input rasters (GDAL-supported)")
    reconstruct_dem.add_argument("--output", type=pathlib.Path, required=True, help="Output DEM raster (GDAL-supported)")
    reconstruct_dem.add_argument("--bbox", type=pathlib.Path, required=True, help="Reconstruction domain as vector layer (GDAL-supported)")
    reconstruct_dem.add_argument("--res", type=float, required=True, help="Target resolution")
    reconstruct_dem.add_argument("--z-prior", type=pathlib.Path, required=True, help="Prior elevation raster (GDAL-supported)")
    reconstruct_dem.add_argument("--output-albedo", type=pathlib.Path, help="Output albedo raster (GDAL-supported)")
    reconstruct_dem.add_argument("--tile-size", type=int, default=768, help="Tile size")
    reconstruct_dem.add_argument("--learning-rate", type=float, default=0.001, help="DEM reconstruction speed/Adam learning rate")
    reconstruct_dem.add_argument("--max-iter", type=int, help="Maximum number of iterations per tile (recommended to prevent infinite loops)")
    reconstruct_dem.add_argument("--tolerance", type=float, default=0.1, help="Minimal elevation difference between two iterations to stop optimisation")
    reconstruct_dem.add_argument("--no-cast-shadows", action="store_true", default=False, help="Turn off shadow casting")
    reconstruct_dem.add_argument("--no-diffuse-sky", action="store_true", default=False, help="Turn off diffuse sky illumination")
    reconstruct_dem.add_argument("--diffuse-sky-n-azimuth", type=int, default=32, help="Number of azimuth directions for diffuse sky illumination calculation")
    reconstruct_dem.add_argument("--diffuse-sky-n-elevation", type=int, default=32, help="Number of elevation directions for diffuse sky illumination calculation")
    reconstruct_dem.add_argument("--diffuse-sky-azimuth-batch-size", type=int, default=1, help="Batch size for traversing azimuth directions for diffuse sky illumination calculation")
    reconstruct_dem.add_argument("--horizon-softness", type=float, default=0.002, help="Softness parameter of horizon operator")

    # forward
    forward = commands.add_parser("forward")
    forward.add_argument("--input", type=pathlib.Path, required=True, help="Input DEM raster (GDAL-supported)")
    forward.add_argument("--output", type=pathlib.Path, required=True, help="Output I/F raster (GDAL-supported)")
    forward.add_argument("--tile-size", type=int, help="Tile size if tiling")
    forward.add_argument("--g", type=float, default=1.0, help="Image gain factor")
    forward.add_argument("--b", type=float, default=0.0, help="Image bias factor")
    forward.add_argument("--d", type=float, default=0.5, help="Diffuse sky gain factor")
    forward.add_argument("--kappa", type=float, default=3.0, help="Diffuse sky anisotropicity parameter")
    forward.add_argument("--albedo", type=path_or_float, default=0.35, help="Albedo (GDAL-supported raster or float)")
    forward.add_argument("--sun-azimuth", type=float, required=True, help="Sun azimuth")
    forward.add_argument("--sun-elevation", type=float, required=True, help="Sun elevation")
    forward.add_argument("--sensor-azimuth", type=float, required=True, help="Sensor azimuth")
    forward.add_argument("--sensor-elevation", type=float, required=True, help="Sensor elevation")
    forward.add_argument("--no-cast-shadows", action="store_true", default=False, help="Turn off shadow casting")
    forward.add_argument("--no-diffuse-sky", action="store_true", default=False, help="Turn off diffuse sky illumination")
    forward.add_argument("--diffuse-sky-n-azimuth", type=int, default=32, help="Number of azimuth directions for diffuse sky illumination calculation")
    forward.add_argument("--diffuse-sky-n-elevation", type=int, default=32, help="Number of elevation directions for diffuse sky illumination calculation")
    forward.add_argument("--diffuse-sky-azimuth-batch-size", type=int, default=1, help="Batch size for traversing azimuth directions for diffuse sky illumination calculation")
    forward.add_argument("--horizon-softness", type=float, default=0.002, help="Softness parameter of horizon operator")
    forward.add_argument("--r", type=pathlib.Path, help="Output raw terrain-unaware illumination (GDAL-supported)")
    forward.add_argument("--sun-factor", type=pathlib.Path, help="Output cast shadows (GDAL-supported)")
    forward.add_argument("--sky-factor", type=pathlib.Path, help="Output diffuse sky contribution before its gain (GDAL-supported)")

    args = parser.parse_args()
    return args


def path_or_float(value):
    try:
        return float(value)
    except ValueError:
        return pathlib.Path(value)


if __name__ == "__main__":
    main()
