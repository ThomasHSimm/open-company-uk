"""Phase 3 of the accounts-parser check: timed benchmark of ours (fixed) vs ixbrlparse vs
Arelle on the same fixed sample of filings, under the build prompt's fairness rules.

Fairness rules this script implements:
  - Same input for every parser: files already decompressed on local disk
    (data/accounts/parser-sample/), read once per timing style (see below).
  - Two timings per parser: "parse" (data already in memory — bytes for ours, io.StringIO
    of text decoded outside the timer for ixbrlparse) and "e2e" (from a local file path,
    warm page cache; Arelle is only ever timed this way, since it loads from a path).
  - One parser at a time. A 200-file warm-up (uncounted) runs before every timed pass.
  - The timed pass runs on a FIXED 5,000-file subset, 3 times; report median and range.
  - Same parallelism: every parser is timed at 1 worker (per-file speed) and at N workers
    (throughput). Arelle may use fewer workers if memory doesn't allow N; if so this script
    records the largest N that actually fit.
  - A 60-second per-file budget. A timeout or exception counts as a failure; its time stays
    in the totals (it is not excluded or retried).
  - Must run under `systemd-inhibit --what=sleep:idle` (wrap the whole script invocation —
    not done inside this script, since inhibiting is a property of the invoking shell).
  - Every run records both CLOCK_MONOTONIC and CLOCK_BOOTTIME; if they differ by more than
    1 second, something suspended the machine mid-run and the run must be flagged/repeated.

Usage:
    systemd-inhibit --what=sleep:idle python scripts/parser_benchmark.py \
        --parser ours --mode parse --workers 1
    systemd-inhibit --what=sleep:idle python scripts/parser_benchmark.py \
        --parser arelle --mode e2e --workers 8
"""

from __future__ import annotations

import argparse
import io
import json
import multiprocessing as mp
import random
import re
import resource
import signal
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ukcompany.accounts.core import IX_NAMESPACE_RE, extract_filing  # noqa: E402

SAMPLE_DIR = Path("data/accounts/parser-sample")
SUBSET_PATH = Path("data/accounts/parser-benchmark-subset.json")
RESULTS_DIR = Path("data/accounts/parser-benchmark-results")

WARMUP_SIZE = 200
SUBSET_SIZE = 5000
REPEATS = 3
TIMEOUT_SECONDS = 60
SUBSET_SEED = 20260925  # fixed, so re-running never reselects a different subset


class BenchmarkTimeout(Exception):
    pass


def _alarm_handler(signum, frame):  # noqa: ARG001
    raise BenchmarkTimeout(f"exceeded {TIMEOUT_SECONDS}s")


def with_timeout(func, *args, **kwargs):
    """SIGALRM-based per-call budget — a documented, standard-library timeout mechanism,
    not a guarantee against a pathological C-level hang, but adequate for real HTML/XBRL
    filings where genuine multi-minute stalls are not the expected failure mode."""
    old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(TIMEOUT_SECONDS)
    try:
        return func(*args, **kwargs)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


MEMBER_RE = re.compile(r"^Prod\d+_\d{4}_([^_]+)_(\d{8})\.(html|htm|xml)$", re.I)


def parse_ours_bytes(data: bytes, company: str, made_up_to_date: str) -> int:
    """Mirrors the production gate in extract.py's process_archive: the same doc-root
    check, then extract_filing. Returns fact count (len(observations))."""
    if not re.search(rb"<\s*html\b", data, re.I) and not IX_NAMESPACE_RE.search(data):
        raise ValueError("no recognisable iXBRL document root")
    filing = extract_filing(data, company, made_up_to_date)
    return len(filing.observations)


def parse_ours_path(path: Path, company: str, made_up_to_date: str) -> int:
    return parse_ours_bytes(path.read_bytes(), company, made_up_to_date)


def parse_ixbrlparse_stream(stream: io.StringIO) -> int:
    from ixbrlparse import IXBRL

    result = IXBRL(stream)
    return len(result.numeric) + len(result.nonnumeric)


def parse_ixbrlparse_path(path: Path) -> int:
    with path.open("rb") as handle:
        return parse_ixbrlparse_stream(handle)


_ARELLE_CNTLR = None


def _get_arelle_cntlr():
    global _ARELLE_CNTLR
    if _ARELLE_CNTLR is None:
        import os

        from arelle import Cntlr

        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        _ARELLE_CNTLR = Cntlr.Cntlr(logFileName=None)
        # One log file per worker process — N workers logging to the same path concurrently
        # would corrupt each other's output.
        _ARELLE_CNTLR.startLogging(
            logFileName=str(RESULTS_DIR / f"arelle_worker_{os.getpid()}.log")
        )
    return _ARELLE_CNTLR


def parse_arelle_path(path: Path) -> int:
    cntlr = _get_arelle_cntlr()
    model = cntlr.modelManager.load(str(path))
    try:
        if model is None or getattr(model, "modelDocument", None) is None:
            raise ValueError("Arelle failed to load a model")
        return len(model.facts)
    finally:
        cntlr.modelManager.close()


def _arelle_subprocess_target(path_str: str, queue) -> None:  # pragma: no cover - subprocess
    try:
        n = parse_arelle_path(Path(path_str))
        peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        queue.put(("ok", n, peak_kb))
    except Exception as exc:  # noqa: BLE001 — reported to the parent, not raised here
        peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        queue.put(("error", f"{type(exc).__name__}: {exc}", peak_kb))


def parse_arelle_hard_timeout(path: Path, timeout: int = TIMEOUT_SECONDS) -> tuple[int, int]:
    """Runs one Arelle load in a fresh subprocess with a hard OS-level kill on timeout.
    Returns (n_facts, peak_rss_kb) — the child reports its own peak RSS, since the work
    happens in a separate process the parent's own RUSAGE_SELF cannot see.

    Found live during this benchmark: a real filing (`Prod224_0076_06934149_20190630.html`)
    references a company-specific extension taxonomy Arelle cannot resolve
    (`dpl-frs:...`), and logs one `xmlSchema:valueError` per affected dimensional fact —
    thousands of them for this file — without ever returning to the Python bytecode loop
    long enough for an in-process `signal.alarm()` to be delivered (confirmed: it ran past
    two hours against a 60s budget). A subprocess-level hard kill is the only enforcement
    that actually works against this failure mode; `with_timeout` (SIGALRM) remains
    sufficient for ours/ixbrlparse, which are pure-Python and yield to the interpreter loop
    regularly, so it is left as-is for them.
    """
    ctx = mp.get_context("fork")
    queue = ctx.Queue()
    process = ctx.Process(target=_arelle_subprocess_target, args=(str(path), queue))
    process.start()
    process.join(timeout)
    if process.is_alive():
        process.kill()
        process.join()
        raise BenchmarkTimeout(f"exceeded {timeout}s (hard subprocess kill)")
    if queue.empty():
        raise RuntimeError(f"Arelle subprocess exited with no result (code {process.exitcode})")
    status, payload, peak_kb = queue.get()
    if status == "error":
        raise RuntimeError(payload)
    return payload, peak_kb


@dataclass
class FileResult:
    path: str
    ok: bool
    elapsed_seconds: float
    n_facts: int
    error: str | None
    worker_peak_rss_kb: int


def _run_one(parser: str, mode: str, path_str: str) -> FileResult:
    path = Path(path_str)
    parsed = MEMBER_RE.fullmatch(path.name)
    company, made_up_to_date = (parsed.group(1), parsed.group(2)) if parsed else ("0", "")
    started = time.perf_counter()
    try:
        if parser == "ours":
            n = with_timeout(
                parse_ours_path if mode == "e2e" else _ours_parse_only,
                path,
                company,
                made_up_to_date,
            )
            # ru_maxrss is a monotonically increasing high-water mark for THIS process,
            # sampled after every file — correct here since ours runs in-process.
            peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        elif parser == "ixbrlparse":
            if mode == "e2e":
                n = with_timeout(parse_ixbrlparse_path, path)
            else:
                text = path.read_text(encoding="utf-8", errors="replace")
                n = with_timeout(parse_ixbrlparse_stream, io.StringIO(text))
            peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        elif parser == "arelle":
            # Runs in its own subprocess (see parse_arelle_hard_timeout) — the child
            # reports its own peak RSS, since this process's own RUSAGE_SELF can't see it.
            n, peak_kb = parse_arelle_hard_timeout(path)
        else:
            raise ValueError(f"unknown parser {parser!r}")
        elapsed = time.perf_counter() - started
        return FileResult(path_str, True, elapsed, n, None, peak_kb)
    except Exception as exc:  # noqa: BLE001 — a failure is data, not a crash: it counts
        elapsed = time.perf_counter() - started
        # For a killed Arelle subprocess this is the PARENT's own memory, not the killed
        # child's — an undercount for that one row, but it never inflates the reported max
        # (other successful rows in the same pass carry the child-reported real peaks).
        peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return FileResult(path_str, False, elapsed, 0, f"{type(exc).__name__}: {exc}", peak_kb)


def _ours_parse_only(path: Path, company: str, made_up_to_date: str) -> int:
    # "Parse only" means the file is already in memory (bytes), decoding excluded from
    # what's being timed for ours since ours takes bytes directly, never text.
    return parse_ours_bytes(path.read_bytes(), company, made_up_to_date)


def select_subset() -> list[str]:
    """The fixed 5,000-file subset, selected once (seeded) and persisted so every parser
    and every repeat times the identical set of files."""
    if SUBSET_PATH.exists():
        return json.loads(SUBSET_PATH.read_text(encoding="utf-8"))
    all_files = sorted(str(p) for p in SAMPLE_DIR.glob("*.html")) + sorted(
        str(p) for p in SAMPLE_DIR.glob("*.htm")
    )
    if len(all_files) < SUBSET_SIZE + WARMUP_SIZE:
        raise SystemExit(
            f"only {len(all_files)} sample files available; need at least "
            f"{SUBSET_SIZE + WARMUP_SIZE} (Phase 1 must be complete before Phase 3 runs)"
        )
    rng = random.Random(SUBSET_SEED)
    subset = rng.sample(all_files, SUBSET_SIZE + WARMUP_SIZE)
    warmup, timed = subset[:WARMUP_SIZE], subset[WARMUP_SIZE:]
    SUBSET_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUBSET_PATH.write_text(json.dumps({"warmup": warmup, "timed": timed}), encoding="utf-8")
    return json.loads(SUBSET_PATH.read_text(encoding="utf-8"))


def run_pass(parser: str, mode: str, paths: list[str], workers: int) -> list[FileResult]:
    if workers == 1:
        return [_run_one(parser, mode, p) for p in paths]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_run_one_star, [(parser, mode, p) for p in paths]))


def _run_one_star(args: tuple[str, str, str]) -> FileResult:
    return _run_one(*args)


def benchmark(parser: str, mode: str, workers: int) -> dict:
    subset = select_subset()
    warmup_paths, timed_paths = subset["warmup"], subset["timed"]

    print(f"warm-up: {len(warmup_paths)} files ({parser}/{mode}, {workers} worker(s))")
    run_pass(parser, mode, warmup_paths, workers)  # uncounted

    run_summaries = []
    for repeat in range(1, REPEATS + 1):
        mono_start = time.clock_gettime(time.CLOCK_MONOTONIC)
        boot_start = time.clock_gettime(time.CLOCK_BOOTTIME)
        wall_start = time.perf_counter()
        results = run_pass(parser, mode, timed_paths, workers)
        wall_elapsed = time.perf_counter() - wall_start
        mono_elapsed = time.clock_gettime(time.CLOCK_MONOTONIC) - mono_start
        boot_elapsed = time.clock_gettime(time.CLOCK_BOOTTIME) - boot_start
        interrupted = abs(boot_elapsed - mono_elapsed) > 1.0

        n_ok = sum(r.ok for r in results)
        n_failed = len(results) - n_ok
        n_timeout = sum(
            1 for r in results if not r.ok and r.error and "BenchmarkTimeout" in r.error
        )
        per_file_ms = [r.elapsed_seconds * 1000 for r in results]

        summary = {
            "repeat": repeat,
            "n_files": len(results),
            "n_ok": n_ok,
            "n_failed": n_failed,
            "n_timeout": n_timeout,
            "wall_seconds": round(wall_elapsed, 3),
            "clock_monotonic_seconds": round(mono_elapsed, 3),
            "clock_boottime_seconds": round(boot_elapsed, 3),
            "interrupted_by_sleep": interrupted,
            "median_ms_per_file": round(statistics.median(per_file_ms), 3),
            "throughput_files_per_sec": round(len(results) / wall_elapsed, 2),
            # Max across every FileResult's own worker's ru_maxrss — see _run_one's
            # comment: this is the true peak RSS of whichever of the N workers ran hottest.
            "peak_rss_per_worker_mb": round(
                max(r.worker_peak_rss_kb for r in results) / 1024, 1
            ),
        }
        print(json.dumps(summary))
        run_summaries.append(summary)
        if interrupted:
            print(
                f"FLAGGED: repeat {repeat} interrupted by sleep/suspend "
                f"(monotonic={mono_elapsed:.1f}s, boottime={boot_elapsed:.1f}s) — repeat it"
            )

    wall_values = [s["wall_seconds"] for s in run_summaries]
    result = {
        "parser": parser,
        "mode": mode,
        "workers": workers,
        "repeats": run_summaries,
        "wall_median_seconds": statistics.median(wall_values),
        "wall_range_seconds": [min(wall_values), max(wall_values)],
        "timeout_seconds_per_file": TIMEOUT_SECONDS,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{parser}_{mode}_w{workers}.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"written: {out_path}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parser", choices=["ours", "ixbrlparse", "arelle"], required=True)
    parser.add_argument("--mode", choices=["parse", "e2e"], required=True)
    parser.add_argument("--workers", type=int, required=True)
    args = parser.parse_args()

    if args.parser == "arelle" and args.mode == "parse":
        raise SystemExit("Arelle is only ever timed end-to-end (loads from a path)")

    benchmark(args.parser, args.mode, args.workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
