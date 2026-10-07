#! /usr/bin/env bash
set -euo pipefail
shopt -s nullglob

usage() {
    local status="${1:-2}"
    echo "Usage: $0 -i INPUT.IMG -o OUTPUT.cub [-e ISIS_CONDA_ENV] [-w yes|no]" >&2
    exit "$status"
}

conda_env="isis"
web="no"
input=""
output=""

while getopts ":i:o:e:w:h" opt; do
    case "$opt" in
        i) input="$OPTARG" ;;
        o) output="$OPTARG" ;;
        e) conda_env="$OPTARG" ;;
        w) web="$OPTARG" ;;
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
stem="${input##*/}"
stem="${stem%.*}"

isis mroctx2isis from="$input" to="$tmpdir/${stem}.cub"
isis spiceinit from="$tmpdir/${stem}.cub" web="$web"

cal_path="$tmpdir/${stem}.cal.cub"
isis ctxcal from="$tmpdir/${stem}.cub" to="$cal_path" iof=yes

spt_sum="$(isis getkey from="$cal_path" grpname=Instrument keyword=SpatialSumming)"
if (( spt_sum == 1 )); then
    isis ctxevenodd from="$cal_path" to="$tmpdir/${stem}.cal.eo.cub"
    cal_path="$tmpdir/${stem}.cal.eo.cub"
fi

isis cam2map from="$cal_path" to="$output" pixres=mpp resolution=4 interp=cubicconvolution
