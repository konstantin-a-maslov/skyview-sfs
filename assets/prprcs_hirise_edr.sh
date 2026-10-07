#! /usr/bin/env bash
set -euo pipefail
shopt -s nullglob

jobs=10
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
input_paths=("${input}"/*.IMG)

for path in "${input_paths[@]}"; do
    wait_for_jobs
    (
        stem="${path##*/}"
        stem="${stem%.*}"

        isis hi2isis from="$path" to="$tmpdir/${stem}.cub"
        isis hical from="$tmpdir/${stem}.cub" to="$tmpdir/${stem}.cal.cub" units=iof
    ) &  
done
wait_all

for f0 in "${tmpdir}"/*_0.cal.cub; do
    [[ -e "$f0" ]] || continue

    common="${f0%_0.cal.cub}"
    f1="${common}_1.cal.cub"

    [[ -e "$f1" ]] || continue

    wait_for_jobs
    (
        isis histitch from1="$f0" from2="$f1" to="${common}.cal.stitch.cub" balance=true
    ) &
done
wait_all

for f in "${tmpdir}"/*.cal.stitch.cub; do
    [[ -e "$f" ]] || continue

    wait_for_jobs
    (
        isis spiceinit from="$f" web="$web"
        isis spicefit from="$f"
    ) &
done
wait_all
          
r5=("${tmpdir}"/*_RED5.cal.stitch.cub)
r5="${r5[0]}"

declare -A ccd_files=()
for f in "${tmpdir}"/*.cal.stitch.cub; do
    [[ -e "$f" ]] || continue

    filename="${f##*/}"

    if [[ "$filename" =~ _RED([0-9])\.cal\.stitch\.cub$ ]]; then
        ccd="${BASH_REMATCH[1]}"
    else
        continue
    fi

    to="${f%.cub}.noproj.cub"
    ccd_files["$ccd"]="$to"

    wait_for_jobs
    (
        isis noproj from="$f" match="$r5" source=frommatch to="$to"
    ) &
done
wait_all

declare -A sample_offsets=()
declare -A line_offsets=()

for ((i=0; i<9; i++)); do
    j=$((i + 1))

    from="${ccd_files[$i]:-}"
    match_ccd="${ccd_files[$j]:-}"

    [[ -n "$from" && -n "$match_ccd" ]] || continue

    flatfile="${tmpdir}/flat_${i}_${j}.txt"
    isis hijitreg from="$from" match="$match_ccd" flatfile="$flatfile"

    sample_offset="$(
        awk '
            /Average Sample Offset:/ {
                line=$0
                sub(/^.*Average Sample Offset:[[:space:]]*/, "", line)
                sub(/[[:space:]]+StdDev:.*$/, "", line)
                print line
                exit
            }
        ' "$flatfile"
    )"
    line_offset="$(
        awk '
            /Average Line Offset:/ {
                line=$0
                sub(/^.*Average Line Offset:[[:space:]]*/, "", line)
                sub(/[[:space:]]+StdDev:.*$/, "", line)
                print line
                exit
            }
        ' "$flatfile"
    )"

    sample_offsets["$i"]="$sample_offset"
    line_offsets["$i"]="$line_offset"
done

mosaic="${tmpdir}/red.mosaic.cub"
cp -- "${ccd_files[5]}" "$mosaic"

sample_sum="1"
line_sum="1"

for ((i=4; i>=0; i--)); do
    from="${ccd_files[$i]:-}"
    [[ -n "$from" ]] || continue

    if [[ -n "${sample_offsets[$i]:-}" ]]; then
        sample_sum="$(
            awk \
                -v a="$sample_sum" \
                -v b="${sample_offsets[$i]}" \
                'BEGIN {printf "%.15g", a + b}'
        )"
        line_sum="$(
            awk \
                -v a="$line_sum" \
                -v b="${line_offsets[$i]}" \
                'BEGIN {printf "%.15g", a + b}'
        )"
    fi

    outsample="$(
        awk \
            -v x="$sample_sum" \
            'BEGIN {print int(x >= 0 ? x + 0.5 : x - 0.5)}'
    )"
    outline="$(
        awk \
            -v x="$line_sum" \
            'BEGIN {print int(x >= 0 ? x + 0.5 : x - 0.5)}'
    )"

    isis handmos from="$from" mosaic="$mosaic" outsample="$outsample" outline="$outline" priority=beneath
done

sample_sum="1"
line_sum="1"

for ((i=6; i<=9; i++)); do
    from="${ccd_files[$i]:-}"
    [[ -n "$from" ]] || continue
    j=$((i - 1))

    if [[ -n "${sample_offsets[$j]:-}" ]]; then
        sample_sum="$(
            awk \
                -v a="$sample_sum" \
                -v b="${sample_offsets[$j]}" \
                'BEGIN {printf "%.15g", a - b}'
        )"
        line_sum="$(
            awk \
                -v a="$line_sum" \
                -v b="${line_offsets[$j]}" \
                'BEGIN {printf "%.15g", a - b}'
        )"
    fi

    outsample="$(
        awk \
            -v x="$sample_sum" \
            'BEGIN {print int(x >= 0 ? x + 0.5 : x - 0.5)}'
    )"
    outline="$(
        awk \
            -v x="$line_sum" \
            'BEGIN {print int(x >= 0 ? x + 0.5 : x - 0.5)}'
    )"

    isis handmos from="$from" mosaic="$mosaic" outsample="$outsample" outline="$outline" priority=beneath
done 

isis cam2map from="$mosaic" to="$output" pixres=camera interp=cubicconvolution
