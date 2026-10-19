#! /usr/bin/env bash
set -euo pipefail
shopt -s nullglob

jobs=$(( $(nproc) < 16 ? $(nproc) : 16 ))
wait_for_jobs() {
    while (( $(jobs -rp | wc -l) >= jobs )); do
        wait -n
    done
}
wait_all() {
    local status=0
    for pid in $(jobs -p); do
        wait "$pid" || status=1
    done
    return "$status"
}

usage() {
    local status="${1:-2}"
    echo "Usage: $0 -i INPUT_FOLDER -o OUTPUT.cub [-e ISIS_CONDA_ENV] [-w yes|no] [-j #JOBS]" >&2
    exit "$status"
}

conda_env="isis"
web="no"
input=""
output=""

while getopts ":i:o:e:w:j:h" opt; do
    case "$opt" in
        i) input="$OPTARG" ;;
        o) output="$OPTARG" ;;
        e) conda_env="$OPTARG" ;;
        w) web="$OPTARG" ;;
        j) jobs="$OPTARG" ;;
        h) usage 0 ;;
        :) echo "Option -$OPTARG requires an argument" >&2; usage ;;
        \?) echo "Unknown option: -$OPTARG" >&2; usage ;;
    esac
done

[[ -n "$input" && -n "$output" ]] || usage

scratch_root="$HOME/TMP"
mkdir -p -- "$scratch_root"
tmpdir="$(mktemp -d "$scratch_root/hirise.XXXXXXXX")"
cleanup() {
    rm -rf -- "$tmpdir"
}
trap cleanup EXIT

isis() {
    conda run -n "$conda_env" "$@"
}

# PROCESSING PIPELINE
input_paths=("${input}"/*.xml)

for path in "${input_paths[@]}"; do
    stem="${path##*/}"
    stem="${stem%.*}"
    
    wait_for_jobs
    (
        isis tgocassis2isis from="$path" to="$tmpdir/${stem}.cub"

        # recover missing spacecraft clock start count before spiceinit
        ts=$(grep -ioE '<em16_tgo_cas:exposuretimestamp>[0-9a-fA-F]+' "$path" | sed 's/.*>//')
        clk=$(printf '%s' "$ts" | xxd -r -p)
        isis editlab from="$tmpdir/${stem}.cub" options=setkey grpname=Instrument keyword=SpacecraftClockStartCount value="$clk"

        isis spiceinit from="$tmpdir/${stem}.cub" web="$web"
        isis footprintinit from="$tmpdir/${stem}.cub"
    ) &  
done
wait_all

printf '%s\n' "$tmpdir"/*.cub > "$tmpdir/cubes.lis"
isis findimageoverlaps fromlist="$tmpdir/cubes.lis" overlaplist="$tmpdir/overlaps.lis"

cat > "$tmpdir/autoseed.def" <<EOF
Group = PolygonSeederAlgorithm
    Name             = Limit
    MinimumThickness = 0.0
    MinimumArea      = 0.0
    MajorAxisPoints  = 32
    MinorAxisPoints  = 4
End_Group
EOF
isis autoseed fromlist="$tmpdir/cubes.lis" overlaplist="$tmpdir/overlaps.lis" deffile="$tmpdir/autoseed.def" onet="$tmpdir/autoseed.net" networkid=cassis pointid="cassis??????" description=none

cat > "$tmpdir/cnetref.def" <<EOF
Group = Operator
    Name            = StandardDeviation
    Samples         = 15
    Lines           = 9
    DeltaSamp       = 10
    DeltaLine       = 4
    MinimumInterest = 0
End_Group
EOF
isis cnetref fromlist="$tmpdir/cubes.lis" cnet="$tmpdir/autoseed.net" onet="$tmpdir/cnetref.net" criteria=interest deffile="$tmpdir/cnetref.def" limit=yes overlaplist="$tmpdir/overlaps.lis"

isis autoregtemplate topvl="$tmpdir/pointreg.def" algorithm=MaximumCorrelation tolerance=0.7 psamp=21 pline=9 ssamp=81 sline=61
isis pointreg fromlist="$tmpdir/cubes.lis" cnet="$tmpdir/cnetref.net" deffile="$tmpdir/pointreg.def" onet="$tmpdir/pointreg.net"

isis jigsaw fromlist="$tmpdir/cubes.lis" cnet="$tmpdir/pointreg.net" onet="$tmpdir/jigsaw.net" update=yes camsolve=angles spsolve=none twist=yes camera_angles_sigma=0.25 maxits=50 

mapfile -t cubes < "$tmpdir/cubes.lis"
isis campt from="${cubes[${#cubes[@]}/2]}" to="$tmpdir/mosaic.geom.pvl" type=image append=no
incidence="$(isis getkey from="$tmpdir/mosaic.geom.pvl" grpname=GroundPoint keyword=Incidence)"
emission="$(isis getkey from="$tmpdir/mosaic.geom.pvl" grpname=GroundPoint keyword=Emission)"
solar_az="$(isis getkey from="$tmpdir/mosaic.geom.pvl" grpname=GroundPoint keyword=SubSolarGroundAzimuth)"
sensor_az="$(isis getkey from="$tmpdir/mosaic.geom.pvl" grpname=GroundPoint keyword=SubSpacecraftGroundAzimuth)"
lat="$(isis getkey from="$tmpdir/mosaic.geom.pvl" grpname=GroundPoint keyword=PlanetocentricLatitude)"
lon="$(isis getkey from="$tmpdir/mosaic.geom.pvl" grpname=GroundPoint keyword=PositiveEast360Longitude)"
solar_longitude="$(isis getkey from="$tmpdir/mosaic.geom.pvl" grpname=GroundPoint keyword=SolarLongitude)"

cat > "$tmpdir/mosaic.scngeomgrp.pvl" <<EOF
Group = SceneGeometry
    ReferencePoint   = CameraImageCenter
    Latitude         = $lat <degrees>
    Longitude        = $lon <degrees>
    SunAzimuth       = $solar_az <degrees>
    SensorAzimuth    = $sensor_az <degrees>
    IncidenceAngle   = $incidence <degrees>
    EmissionAngle    = $emission <degrees>
    SolarLongitude   = $solar_longitude <degrees>
End_Group
End
EOF

isis maptemplate map="$tmpdir/extent.map" fromlist="$tmpdir/cubes.lis" clon=0 rngopt=calc
minlon=$(isis getkey from="$tmpdir/extent.map" grpname=Mapping keyword=MinimumLongitude)
maxlon=$(isis getkey from="$tmpdir/extent.map" grpname=Mapping keyword=MaximumLongitude)
clon=$(awk -v min="$minlon" -v max="$maxlon" 'BEGIN {printf "%.6f", (min+max)/2}')
isis maptemplate map="$tmpdir/framelets.map" projection=sinusoidal clon="$clon" resopt=mpp resolution=3
for path in "$tmpdir"/*.cub; do
    stem="${path##*/}"
    stem="${stem%.cub}"

    wait_for_jobs
    (
        isis cam2map from="$path" to="$tmpdir/${stem}.proj.cub" map="$tmpdir/framelets.map" pixres=map interp=cubicconvolution
    ) &
done
wait_all

printf '%s\n' "$tmpdir"/*.proj.cub > "$tmpdir/proj.lis"
isis tgocassismos fromlist="$tmpdir/proj.lis" to="$output"
isis editlab from="$output" option=addtemp tempfile="$tmpdir/mosaic.scngeomgrp.pvl"
isis editlab from="$output" options=delg grpname=Tracking
rm -f -- "${output%.cub}_tracking.cub"
