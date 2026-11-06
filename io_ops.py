import rioxarray
import pvl
import xarray
import rasterio
import numpy as np
import pyproj
import re


def read_scene(path):
    scene = rioxarray.open_rasterio(path, masked=True)[0]
    return scene

    
def read_scene_from_cub(path):
    scene = rioxarray.open_rasterio(path, masked=True)[0]
    label = pvl.load(path)

    attrs = {
        normalise_label_key(key): float(label["IsisCube"]["SceneGeometry"][key])
        for key in [
            "Latitude",
            "Longitude",
            "SunAzimuth",
            "SensorAzimuth",
            "IncidenceAngle",
            "EmissionAngle",
            "SolarLongitude",
        ]
    }

    attrs["sun_elevation"] = 90.0 - attrs["incidence_angle"]
    attrs["sensor_elevation"] = 90.0 - attrs["emission_angle"]

    scene.attrs.update(attrs)

    return scene


def write(product, path, allow_cog=True):
    path.parents[0].mkdir(parents=True, exist_ok=True)
    if allow_cog and path.suffix in {".tif", ".tiff", ".TIF", ".TIFF"}:
        write_as_cog(product, path)
        return
    product.rio.to_raster(path)


def write_as_cog(product, path):
    product.rio.to_raster(
        path,
        driver="COG",
        compress="LZW",
        blocksize=512,
        predictor=3,
        num_threads="ALL_CPUS",
        overview_resampling="average",
        BIGTIFF="IF_SAFER",
    )


def write_array_with_georef(array, georef, path, name="", drop_attrs=True, attrs=None, allow_cog=True):
    rst = georef.copy(deep=False).rename(name)
    if drop_attrs:
        rst.attrs = {}
    if attrs:
        rst.attrs.update(attrs)
    rst.data[...] = array[...]
    write(rst, path, allow_cog=allow_cog)


def convert_azimuths_to_image_space(scene):
    attrs = {
        "sun_azimuth_img": to_image_azimuth(scene, scene.attrs["sun_azimuth"]),
        "sensor_azimuth_img": to_image_azimuth(scene, scene.attrs["sensor_azimuth"]),
    }
    scene.attrs.update(attrs)
    return scene


def get_named(container, kind, name):
    return next(item for item in container.getlist(kind) if item.get("Name") == name)


def normalise_label_key(key):
    key = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', key)
    key = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', key)
    return key.lower()


def to_image_azimuth(scene, azimuth, step_m=10):
    crs = pyproj.CRS.from_user_input(scene.rio.crs)
    geo_crs = crs.geodetic_crs

    to_map = pyproj.Transformer.from_crs(geo_crs, crs, always_xy=True)
    to_geo = pyproj.Transformer.from_crs(crs, geo_crs, always_xy=True)

    affine = scene.rio.transform()
    inverse_affine = ~affine

    x, y = affine * (scene.sizes["x"] / 2, scene.sizes["y"] / 2)
    lon, lat = to_geo.transform(x, y)

    geod = geo_crs.get_geod()
    lon2, lat2, _ = geod.fwd(lon, lat, azimuth, step_m)

    x1, y1 = to_map.transform(lon, lat)
    x2, y2 = to_map.transform(lon2, lat2)

    col1, row1 = inverse_affine * (x1, y1)
    col2, row2 = inverse_affine * (x2, y2)

    dcol = col2 - col1
    drow = row2 - row1

    return float(np.degrees(np.arctan2(dcol, -drow)) % 360)


def create_grid(bbox, res, proj_str=None):
    if proj_str is None:
        bbox_sphere = bbox.to_crs("ESRI:104971")
        lon_min, lat_min, lon_max, lat_max = bbox_sphere.geometry.total_bounds
        lat_0, lon_0 = (lat_min + lat_max) /  2, (lon_min + lon_max) / 2
        proj_str = f"+proj=aeqd +lat_0={lat_0} +lon_0={lon_0} +R=3396190 +x_0=0 +y_0=0 +units=m +no_defs +type=crs"
    
    xmin, ymin, xmax, ymax = bbox.to_crs(proj_str).total_bounds

    nx = max(1, int(np.ceil((xmax - xmin) / res)))
    ny = max(1, int(np.ceil((ymax - ymin) / res)))

    transform = rasterio.transform.from_origin(xmin, ymax, res, res)

    x = xmin + (np.arange(nx) + 0.5) * res
    y = ymax - (np.arange(ny) + 0.5) * res

    grid = xarray.DataArray(
        np.full((ny, nx), np.nan, dtype=np.float32),
        dims=("y", "x"),
        coords={"x": x, "y": y},
        name="grid",
    )
    grid = grid.rio.write_crs(proj_str)
    grid = grid.rio.write_transform(transform)

    return grid
