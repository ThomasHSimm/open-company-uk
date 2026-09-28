#!/bin/bash
# Runs the full Phase 3 benchmark matrix, one parser at a time, in the order fastest-first
# so mechanics are re-validated on real data before committing to Arelle's slow passes.
# Each combination is independently resumable: if data/accounts/parser-benchmark-results/
# already has a given combo's output file, it is skipped.
set -e
cd /home/tsispace/Documents/GitHub/open-company-uk
PY=/home/tsispace/miniconda3/envs/env1/bin/python
RESULTS=data/accounts/parser-benchmark-results

run_combo() {
    local parser=$1 mode=$2 workers=$3
    local outfile="$RESULTS/${parser}_${mode}_w${workers}.json"
    if [ -f "$outfile" ]; then
        echo "SKIP (already done): $parser/$mode/w$workers"
        return
    fi
    echo "=== RUNNING: $parser / $mode / $workers worker(s) === $(date -Iseconds)"
    $PY scripts/parser_benchmark.py --parser "$parser" --mode "$mode" --workers "$workers"
    echo "=== DONE: $parser / $mode / $workers worker(s) === $(date -Iseconds)"
}

run_combo ours parse 1
run_combo ours parse 8
run_combo ours e2e 1
run_combo ours e2e 8
run_combo ixbrlparse parse 1
run_combo ixbrlparse parse 8
run_combo ixbrlparse e2e 1
run_combo ixbrlparse e2e 8
run_combo arelle e2e 1
run_combo arelle e2e 8

echo "=== PHASE 3 MATRIX COMPLETE === $(date -Iseconds)"
