#!/bin/bash
# Phase D2 (accounts-parser v2 rebuild): 8-way month-range parallel launch of the
# production `ukcompany-accounts run` pipeline, which has no built-in parallelism of its
# own (confirmed live: single-threaded throughput was ~820 filings/sec, projecting ~12h for
# the full archive against the brief's ~4-5h estimate). Each worker gets its own --store
# (disposable-store manifest only; SQLite doesn't tolerate concurrent writers to one file)
# but all workers share the same --output-dir, since per-month Parquet filenames
# (accounts-long-YYYY-MM.parquet) never collide across disjoint month ranges.
set -e
cd /home/tsispace/Documents/GitHub/open-company-uk
PY=/home/tsispace/miniconda3/envs/env1/bin/ukcompany-accounts
OUT=data/accounts/v2
LOGDIR=/tmp/claude-1000/-home-tsispace-Documents-GitHub-open-company-uk/364f1c87-da7d-462b-8400-f00e0ea187b2/scratchpad

declare -a RANGES=(
  "2014-01 2015-07"
  "2015-08 2017-02"
  "2017-03 2018-09"
  "2018-10 2020-04"
  "2020-05 2021-11"
  "2021-12 2023-06"
  "2023-07 2025-01"
  "2025-02 2026-08"
)

mkdir -p "$OUT/long"

for i in "${!RANGES[@]}"; do
  n=$((i + 1))
  read -r from to <<< "${RANGES[$i]}"
  systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 --unit="phase-d2-worker-$n" -- \
    "$PY" run \
      --from "$from" --to "$to" \
      --store "$OUT/manifest_$n.sqlite" \
      --output-dir "$OUT/long" \
      --coverage-report "$OUT/accounts-coverage_$n.md" \
      --report "$OUT/accounts-extraction_$n.md" \
      --disposable-store \
    > "$LOGDIR/phase_d2_worker_$n.log" 2>&1 &
  echo "launched worker $n: $from..$to (pid $!)"
done

wait
echo "=== ALL WORKERS FINISHED ==="
