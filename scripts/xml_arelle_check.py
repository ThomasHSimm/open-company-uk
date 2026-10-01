"""Phase C: check the XML adapter (xml_adapter.extract_filing_xml, via ixbrlparse) against
Arelle on a sample of real plain-XBRL `.xml` filings — an independent, standards-based
cross-check that the adapter's facts are genuinely correct, not just "doesn't crash".

Not timed. Reuses the same hard-subprocess-timeout Arelle wrapper as
scripts/arelle_correctness.py (nested multiprocessing: an outer pool worker per file, each
spawning its own short-lived inner subprocess for the 60s hard kill) — the same design
already proven safe against a real pathological filing during Phase 3.

Usage:
    python scripts/xml_arelle_check.py
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from arelle_correctness import arelle_facts_hard_timeout  # noqa: E402
from parser_compare import MEMBER_RE, FactKey, values_equal  # noqa: E402

from ukcompany.accounts.xml_adapter import extract_filing_xml  # noqa: E402

SAMPLE_DIR = Path("data/accounts/parser-sample")
SAMPLE_SIZE = 200
SEED = 20260927
RESULTS_PATH = Path("data/accounts/parser-compare-results/xml_adapter_vs_arelle.json")


def ours_xml_facts(data: bytes, company: str, made_up_to_date: str, member: str) -> dict[FactKey, str]:
    filing = extract_filing_xml(data, company, made_up_to_date)
    facts: dict[FactKey, str] = {}
    for obs in filing.observations:
        dims = ((obs.dimension, obs.member),) if obs.dimension else ()
        key = FactKey(company, member, obs.concept, obs.period_end, dims)
        value = obs.numeric_value if obs.numeric_value is not None else obs.raw_value
        facts[key] = value
    return facts


def _process_one(path_str: str) -> dict:
    path = Path(path_str)
    member = path.name
    parsed = MEMBER_RE.fullmatch(member)
    if not parsed:
        return {"status": "skipped", "member": member}
    company, made_up_to_date, _extension = parsed.groups()
    data = path.read_bytes()

    try:
        ours = ours_xml_facts(data, company, made_up_to_date, member)
    except Exception as exc:  # noqa: BLE001
        return {"status": "ours_failed", "member": member, "error": f"{type(exc).__name__}: {exc}"}
    try:
        arelle = arelle_facts_hard_timeout(path, company, member)
    except TimeoutError:
        return {"status": "arelle_timeout", "member": member}
    except Exception as exc:  # noqa: BLE001
        return {"status": "arelle_failed", "member": member, "error": f"{type(exc).__name__}: {exc}"}

    ours_keys, arelle_keys = set(ours), set(arelle)
    shared = ours_keys & arelle_keys
    agree = sum(1 for key in shared if values_equal(ours[key], arelle[key]))
    disagreements = [
        {"key": str(key), "ours": ours[key], "arelle": arelle[key]}
        for key in shared
        if not values_equal(ours[key], arelle[key])
    ][:3]
    return {
        "status": "ok",
        "member": member,
        "ours_total": len(ours_keys),
        "arelle_total": len(arelle_keys),
        "shared": len(shared),
        "agree": agree,
        "ours_only": len(ours_keys - arelle_keys),
        "arelle_only": len(arelle_keys - ours_keys),
        "disagreement_examples": disagreements,
    }


def main() -> int:
    all_xml = sorted(p.name for p in SAMPLE_DIR.glob("*.xml"))
    rng = random.Random(SEED)
    chosen = rng.sample(all_xml, min(SAMPLE_SIZE, len(all_xml)))
    paths = [str(SAMPLE_DIR / member) for member in chosen]
    print(f"checking {len(paths)} XML filings against Arelle")

    results = []
    with ProcessPoolExecutor(max_workers=8) as pool:
        for i, result in enumerate(pool.map(_process_one, paths), 1):
            results.append(result)
            if i % 50 == 0:
                print(f"  ... {i}/{len(paths)} processed", flush=True)

    status_counts = Counter(r["status"] for r in results)
    ok = [r for r in results if r["status"] == "ok"]
    total_shared = sum(r["shared"] for r in ok)
    total_agree = sum(r["agree"] for r in ok)
    total_ours_only = sum(r["ours_only"] for r in ok)
    total_arelle_only = sum(r["arelle_only"] for r in ok)

    summary = {
        "sample_size": len(paths),
        "status_counts": dict(status_counts),
        "files_compared": len(ok),
        "total_shared_facts": total_shared,
        "total_agree": total_agree,
        "agreement_rate": round(total_agree / total_shared, 4) if total_shared else None,
        "total_ours_only": total_ours_only,
        "total_arelle_only": total_arelle_only,
        "per_file": results,
    }
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"written: {RESULTS_PATH}")
    print(json.dumps({k: v for k, v in summary.items() if k != "per_file"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
