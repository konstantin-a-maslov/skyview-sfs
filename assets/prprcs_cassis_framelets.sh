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

tmpdir="$(mktemp -d)"
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

# findimageoverlaps
# autoseed
# pointreg
# jigsaw update=yes
# cam2map
# tgocassismos

# isis cam2map from="$XXX" to="$output" pixres=mpp resolution=3 interp=cubicconvolution