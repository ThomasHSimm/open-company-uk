"""Phase 3 point 3 / Phase 4 "who does Arelle agree with": a third, independent parser run
over the filings where ours and ixbrlparse disagree, to see which one Arelle's own model
resolution sides with, broken down by disagreement type.

Not a timed pass (Phase 3's speed numbers come only from parser_benchmark.py). Runs each
file exactly once, one worker, with the same hard-subprocess-timeout Arelle wrapper used in
Phase 3 (see parser_benchmark.parse_arelle_hard_timeout's docstring for why an in-process
SIGALRM is not safe for Arelle).

Correctness-set composition (a scope decision, flagged here rather than silently assumed):
  1. Every file in Phase 4's fixed 5,000-file subset that Phase 4 flagged as disagreeing
     (`disagreeing_members` in data/accounts/parser-compare-results/ours_vs_ixbrlparse.json)
     — this is almost the entire subset (4,977 / 5,000), since "disagreement" here is any
     shared-key value difference, ixbrlparse-only fact, or ours-only fact, not just the
     large structural gaps.
  2. A random top-up of FILL_SIZE additional filings drawn from the wider 356,469-file
     sample, EXCLUDING every file already in the 5,000-file subset, so Arelle also gets
     exposure to filings neither Phase 3 nor Phase 4 already touched.
FILL_SIZE is sized from Phase 3's measured Arelle 8-worker throughput (~4.4 files/sec,
data/accounts/parser-benchmark-results/arelle_e2e_w8.json) to keep this pass to roughly
30 minutes total: (4,977 + 3,000) / 4.4 ~= 30 minutes. This is a judgement call, not a
maintainer instruction — flagged in docs/accounts-parser-check.md.

Fact matching is best-effort, not the same rigorously-reconciled FactKey used between ours
and ixbrlparse (see parser_compare.py): Arelle's own context/period model is date-shifted
(an instant "2023-07-31" surfaces as ctx.instantDatetime == 2023-08-01, XBRL's exclusive-end
convention — confirmed by probing a real filing before writing this), so period_end here is
recovered by subtracting one day. Joins on (concept local name, period_end, sorted dimension
member local names) — the same shape as FactKey, but independently computed, so a mismatch
in one of the three key fields (rather than the value) would show as "key not found",
indistinguishable from Arelle genuinely not producing that fact. Reported as an explicit
limitation in the report, not silently smoothed over.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import random
import resource
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from parser_compare import (  # noqa: E402
    MEMBER_RE,
    SUBSET_PATH,
    FactKey,
    categorise_missing,
    ixbrlparse_facts,
    mismatch_reason,
    ours_facts,
    values_equal,
)

SAMPLE_DIR = Path("data/accounts/parser-sample")
COMPARE_RESULTS = Path("data/accounts/parser-compare-results/ours_vs_ixbrlparse.json")
RESULTS_DIR = Path("data/accounts/parser-benchmark-results")
OUT_PATH = Path("data/accounts/parser-compare-results/arelle_correctness.json")

FILL_SIZE = 3000
FILL_SEED = 20260925  # same seed convention as parser_benchmark's subset selection
TIMEOUT_SECONDS = 60


def build_correctness_set() -> tuple[list[str], dict]:
    subset = json.loads(SUBSET_PATH.read_text(encoding="utf-8"))
    timed_paths = subset["timed"]
    timed_members = {Path(p).name for p in timed_paths}
    timed_by_member = {Path(p).name: p for p in timed_paths}

    compare = json.loads(COMPARE_RESULTS.read_text(encoding="utf-8"))
    disagreeing = compare["disagreeing_members"]
    disagreeing_paths = [timed_by_member[m] for m in disagreeing if m in timed_by_member]

    all_sample_members = {p.name for p in SAMPLE_DIR.glob("*.html")} | {
        p.name for p in SAMPLE_DIR.glob("*.htm")
    }
    fill_pool = sorted(all_sample_members - timed_members)
    rng = random.Random(FILL_SEED)
    fill_members = rng.sample(fill_pool, min(FILL_SIZE, len(fill_pool)))
    fill_paths = [str(SAMPLE_DIR / m) for m in fill_members]

    coverage = {
        "disagreeing_in_subset": len(compare["disagreeing_members"]),
        "disagreeing_resolved_to_paths": len(disagreeing_paths),
        "fill_pool_available": len(fill_pool),
        "fill_requested": FILL_SIZE,
        "fill_used": len(fill_members),
        "total_correctness_set": len(disagreeing_paths) + len(fill_paths),
    }
    return disagreeing_paths + fill_paths, coverage


def _arelle_facts_from_model(model, company: str, member: str) -> dict[FactKey, str]:
    facts: dict[FactKey, str] = {}
    for fact in model.facts:
        if fact.concept is None or fact.context is None or fact.isNil:
            continue
        ctx = fact.context
        if ctx.isInstantPeriod:
            end_dt = ctx.instantDatetime
        else:
            end_dt = ctx.endDatetime
        if end_dt is None:
            continue
        period_end = (end_dt - timedelta(days=1)).date().isoformat()
        dims = tuple(
            sorted(
                (
                    dim_qname.localName,
                    (
                        dim_value.memberQname.localName
                        if dim_value.memberQname is not None
                        else str(dim_value.typedMember)
                    ),
                )
                for dim_qname, dim_value in (ctx.qnameDims or {}).items()
            )
        )
        try:
            value = str(fact.xValue) if fact.concept.isNumeric else str(fact.value)
        except Exception:  # noqa: BLE001 — a handful of facts have unresolvable xValue
            value = str(fact.value)
        key = FactKey(company, member, fact.concept.qname.localName, period_end, dims)
        facts[key] = value
    return facts


def _arelle_subprocess_target(path_str: str, company: str, member: str, queue) -> None:  # pragma: no cover
    try:
        from arelle import Cntlr

        cntlr = Cntlr.Cntlr(logFileName=None)
        cntlr.startLogging(logFileName=str(RESULTS_DIR / f"arelle_correctness_{__import__('os').getpid()}.log"))
        model = cntlr.modelManager.load(path_str)
        if model is None or getattr(model, "modelDocument", None) is None:
            raise ValueError("Arelle failed to load a model")
        facts = _arelle_facts_from_model(model, company, member)
        cntlr.modelManager.close()
        peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        queue.put(("ok", facts, peak_kb))
    except Exception as exc:  # noqa: BLE001 — reported to the parent, not raised here
        peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        queue.put(("error", f"{type(exc).__name__}: {exc}", peak_kb))


def arelle_facts_hard_timeout(path: Path, company: str, member: str) -> dict[FactKey, str]:
    ctx = mp.get_context("fork")
    queue = ctx.Queue()
    process = ctx.Process(
        target=_arelle_subprocess_target, args=(str(path), company, member, queue)
    )
    process.start()
    process.join(TIMEOUT_SECONDS)
    if process.is_alive():
        process.kill()
        process.join()
        raise TimeoutError(f"exceeded {TIMEOUT_SECONDS}s (hard subprocess kill)")
    if queue.empty():
        raise RuntimeError(f"Arelle subprocess exited with no result (code {process.exitcode})")
    status, payload, _peak_kb = queue.get()
    if status == "error":
        raise RuntimeError(payload)
    return payload


def verdict(disagreement_arelle_value: str | None, ours_value: str, ixbrl_value: str) -> str:
    if disagreement_arelle_value is None:
        return "arelle_missing_key"
    agrees_ours = values_equal(disagreement_arelle_value, ours_value)
    agrees_ixbrl = values_equal(disagreement_arelle_value, ixbrl_value)
    if agrees_ours and agrees_ixbrl:
        return "arelle_agrees_both"
    if agrees_ours:
        return "arelle_agrees_ours"
    if agrees_ixbrl:
        return "arelle_agrees_ixbrlparse"
    return "arelle_agrees_neither"


def _process_one(path_str: str) -> dict:
    """One correctness-set file, run inside an outer pool worker. Computes ours-vs-ixbrlparse
    disagreements exactly as parser_compare.compare_all does, then — only if there ARE any
    disagreements for this file — spawns Arelle in ITS OWN inner subprocess (hard timeout,
    same as Phase 3) to see which side, if either, Arelle's value matches. Nested
    multiprocessing (outer pool worker forking an inner single-purpose subprocess) is
    intentional: the inner fork is what gives the 60s hard kill; the outer pool is what
    gives the throughput to fit this pass inside its stated time budget."""
    path = Path(path_str)
    member = path.name
    parsed = MEMBER_RE.fullmatch(member)
    if not parsed:
        return {"status": "skipped"}
    company, made_up_to_date, extension = parsed.groups()
    is_xml = extension.lower() == "xml"
    data = path.read_bytes()

    try:
        ours = ours_facts(data, company, made_up_to_date, member) if not is_xml else {}
    except Exception:  # noqa: BLE001
        ours = {}
    try:
        ixbrl, formats = ixbrlparse_facts(data, company, member)
    except Exception:  # noqa: BLE001
        ixbrl, formats = {}, {}

    ours_keys, ixbrl_keys = set(ours), set(ixbrl)
    shared = ours_keys & ixbrl_keys
    disagreements: list[tuple[FactKey, str, str, str]] = []
    for key in shared:
        if not values_equal(ours[key], ixbrl[key]):
            reason = mismatch_reason(ours[key], ixbrl[key], formats.get(key))
            disagreements.append((key, f"value_mismatch_{reason}", ours[key], ixbrl[key]))
    for key in ixbrl_keys - ours_keys:
        reason = categorise_missing(key, path, data, is_xml)
        disagreements.append((key, f"ixbrlparse_only_{reason}", "", ixbrl[key]))
    for key in ours_keys - ixbrl_keys:
        disagreements.append((key, "ours_only", ours[key], ""))

    if not disagreements:
        return {"status": "no_disagreement"}

    try:
        arelle = arelle_facts_hard_timeout(path, company, member)
    except TimeoutError:
        return {"status": "timeout"}
    except Exception:  # noqa: BLE001
        return {"status": "failed"}

    verdicts = []
    for key, reason, ours_val, ixbrl_val in disagreements:
        arelle_val = arelle.get(key)
        v = verdict(arelle_val, ours_val, ixbrl_val)
        verdicts.append((reason, v, str(key), ours_val, ixbrl_val, arelle_val))
    return {"status": "ok", "verdicts": verdicts}


def run(paths: list[str], workers: int) -> dict:
    from concurrent.futures import ProcessPoolExecutor

    by_reason: dict[str, dict[str, int]] = {}
    file_ok = file_failed = file_timeout = file_no_disagreement = 0
    examples: dict[str, list] = {}

    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i, outcome in enumerate(pool.map(_process_one, paths), 1):
            status = outcome["status"]
            if status == "ok":
                file_ok += 1
                for reason, v, key, ours_val, ixbrl_val, arelle_val in outcome["verdicts"]:
                    bucket = by_reason.setdefault(reason, {})
                    bucket[v] = bucket.get(v, 0) + 1
                    ex_bucket = examples.setdefault(f"{reason}__{v}", [])
                    if len(ex_bucket) < 3:
                        ex_bucket.append(
                            {
                                "key": key,
                                "ours": ours_val,
                                "ixbrlparse": ixbrl_val,
                                "arelle": arelle_val,
                            }
                        )
            elif status == "timeout":
                file_timeout += 1
            elif status == "failed":
                file_failed += 1
            elif status == "no_disagreement":
                file_no_disagreement += 1

            if i % 200 == 0:
                print(f"  ... {i}/{len(paths)} files processed", flush=True)

    return {
        "files_attempted": len(paths),
        "files_ok": file_ok,
        "files_no_disagreement": file_no_disagreement,
        "files_failed": file_failed,
        "files_timeout": file_timeout,
        "by_reason": by_reason,
        "examples": examples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    correctness_paths, coverage = build_correctness_set()
    print(f"correctness set: {json.dumps(coverage)}")

    started = time.perf_counter()
    result = run(correctness_paths, args.workers)
    elapsed = time.perf_counter() - started
    result["coverage"] = coverage
    result["wall_seconds"] = round(elapsed, 1)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"written: {OUT_PATH} ({elapsed:.1f}s)")
    print(json.dumps(result["by_reason"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
