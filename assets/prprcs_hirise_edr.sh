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
isisdata="$(conda run -n "$conda_env" bash -lc 'printf "%s" "$ISISDATA"')"


# PROCESSING PIPELINE
input_paths=("${input}"/*.IMG)

for path in "${input_paths[@]}"; do
    stem="${path##*/}"
    stem="${stem%.*}"
    
    wait_for_jobs
    (
        isis hi2isis from="$path" to="$tmpdir/${stem}.cub"
        isis spiceinit from="$tmpdir/${stem}.cub" web="$web"
        isis hical from="$tmpdir/${stem}.cub" to="$tmpdir/${stem}.cal.cub" units=iof

        summing="$(isis getkey from="$tmpdir/${stem}.cal.cub" grpname=Instrument keyword=Summing)"
        ccd="$(isis getkey from="$tmpdir/${stem}.cal.cub" grpname=Instrument keyword=CcdId)"
        channel="$(isis getkey from="$tmpdir/${stem}.cal.cub" grpname=Instrument keyword=ChannelNumber)"

        coeff_file="$isisdata/mro/calibration/HiRISE_Gain_Drift_Correction_Bin${summing}.0001.csv"
        coeffs="$(
            awk -F',' -v key="${ccd}_${channel}" '
                function trim(s) {
                    gsub(/^[[:space:]]+|[[:space:]]+$/, "", s)
                    return s
                }
                {
                    name = trim($1)
                    if (name == key) {
                        for (i = 2; i <= 5; i++) {
                            value = trim($i)
                            sub(/^-/, "", value)
                            printf "%s%s", value, (i < 5 ? OFS : ORS)
                        }
                        exit
                    }
                }
            ' "$coeff_file"
        )"
        if [[ -z "$coeffs" ]]; then
            echo "No gain-drift coefficients found for ${ccd}_${channel} in $coeff_file" >&2
            exit 1
        fi
        read -r r0 r1 r2 max_line <<< "$coeffs"

        equation="\((F1/(${r0}+(${r1}*line)+(${r2}*line*line)))*(line<${max_line})+(F1*(line>=${max_line})))"
        isis fx f1="$tmpdir/${stem}.cal.cub" to="$tmpdir/${stem}.cal.fx.cub" mode=cubes equation="$equation"

        # if [[ "$summing" == "1" || "$summing" == "2" ]]; then
        #     isis hidestripe from="$tmpdir/${stem}.cal.fx.cub" to="$tmpdir/${stem}.cal.fx.hstmp.cub" parity=even correction=add
        #     isis hidestripe from="$tmpdir/${stem}.cal.fx.hstmp.cub" to="$tmpdir/${stem}.cal.fx.hs.cub" parity=odd correction=add
        # else
        #     isis hidestripe from="$tmpdir/${stem}.cal.fx.cub" to="$tmpdir/${stem}.cal.fx.hs.cub" parity=auto correction=add
        # fi
    ) &  
done
wait_all

for f0 in "${tmpdir}"/*_0.cal.fx.cub; do
    [[ -e "$f0" ]] || continue

    common="${f0%_0.cal.fx.cub}"
    f1="${common}_1.cal.fx.cub"

    [[ -e "$f1" ]] || continue

    wait_for_jobs
    (
        isis histitch from1="$f0" from2="$f1" to="${common}.cal.fx.stitch.cub" balance=true
    ) &
done
wait_all

hiequal_from="$tmpdir/hiequal_from.lis"
hiequal_hold="$tmpdir/hiequal_hold.lis"
hiequal_to="$tmpdir/hiequal_to.lis"
: > "$hiequal_from"
: > "$hiequal_hold"
: > "$hiequal_to"

for ((i=0; i<=9; i++)); do
    matches=("${tmpdir}"/*_RED${i}.cal.fx.stitch.cub)
    if (( ${#matches[@]} != 1 )); then
        continue
    fi
    f="${matches[0]}"
    equ="${f%.cub}.equ.cub"
    printf '%s\n' "$f"   >> "$hiequal_from"
    printf '%s\n' "$equ" >> "$hiequal_to"
    if (( i == 5 )); then
        printf '%s\n' "$f" >> "$hiequal_hold"
    fi
done

isis hiequal fromlist="$hiequal_from" holdlist="$hiequal_hold" tolist="$hiequal_to" process=both

for f in "${tmpdir}"/*.cal.fx.stitch.equ.cub; do
    [[ -e "$f" ]] || continue

    wait_for_jobs
    (
        isis spiceinit from="$f" web="$web"
        isis spicefit from="$f"
    ) &
done
wait_all
          
r5=("${tmpdir}"/*_RED5.cal.fx.stitch.equ.cub)
r5="${r5[0]}"

declare -A ccd_files=()
for f in "${tmpdir}"/*.cal.fx.stitch.equ.cub; do
    [[ -e "$f" ]] || continue

    filename="${f##*/}"

    if [[ "$filename" =~ _RED([0-9])\.cal\.fx\.stitch\.equ\.cub$ ]]; then
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
