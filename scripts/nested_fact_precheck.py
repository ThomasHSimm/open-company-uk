"""Phase B1 pre-check (per maintainer's reduced-scope decision): before touching core.py,
split the existing Phase 4 nested_fact disagreements (both the value-mismatch and
ixbrlparse-only variants) into numeric vs non-numeric, and report which concepts are
affected. The stack-based nesting-aware scan (the real fix) is only worth building if numeric
inner facts are lost at a material rate: >0.1% of numeric facts, or any core WIDE concept
(config/accounts-wide-columns.json) is affected at all.

Reuses parser_compare.py's comparison logic and phase_a_analysis.py's fact-kind-aware
wrappers completely unmodified — this is read-only analysis of the same fixed 5,000-file
subset, not a rerun with different parsing.

Usage:
    python scripts/nested_fact_precheck.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from parser_compare import (  # noqa: E402
    CENSUS_DIR,
    MEMBER_RE,
    SUBSET_PATH,
    categorise_missing,
    load_year_lookup,
    mismatch_reason,
    values_equal,
)
from phase_a_analysis import (  # noqa: E402
    ixbrlparse_facts_with_kind,
    ours_facts_with_kind,
)

WIDE_COLUMNS_CONFIG = Path("config/accounts-wide-columns.json")
RESULTS_DIR = Path("data/accounts/parser-compare-results")


def load_wide_concepts() -> set[str]:
    config = json.loads(WIDE_COLUMNS_CONFIG.read_text(encoding="utf-8"))
    concepts = set(config["totals"])
    concepts.update(member["concept"] for member in config["members"])
    return concepts


def main() -> int:
    subset = json.loads(SUBSET_PATH.read_text(encoding="utf-8"))
    paths = subset["timed"]
    year_lookup = load_year_lookup(CENSUS_DIR)
    wide_concepts = load_wide_concepts()

    # value-mismatch nested_fact, split by kind, with concept counters
    vm_by_kind: Counter[str] = Counter()
    vm_concepts_numeric: Counter[str] = Counter()
    vm_concepts_nonnumeric: Counter[str] = Counter()

    # ixbrlparse-only nested_fact, split by kind, with concept counters
    io_by_kind: Counter[str] = Counter()
    io_concepts_numeric: Counter[str] = Counter()
    io_concepts_nonnumeric: Counter[str] = Counter()

    total_numeric_facts_ixbrlparse = 0
    wide_concept_hits: list[dict] = []
    n_processed = 0

    for path_str in paths:
        path = Path(path_str)
        member = path.name
        parsed = MEMBER_RE.fullmatch(member)
        if not parsed:
            continue
        company, made_up_to_date, extension = parsed.groups()
        is_xml = extension.lower() == "xml"
        year = year_lookup.get(member)
        if year is None:
            continue
        data = path.read_bytes()

        try:
            ours, ours_kinds = (
                ours_facts_with_kind(data, company, made_up_to_date, member)
                if not is_xml
                else ({}, {})
            )
        except Exception:  # noqa: BLE001
            ours, ours_kinds = {}, {}
        try:
            ixbrl, formats, ixbrl_kinds = ixbrlparse_facts_with_kind(data, company, member)
        except Exception:  # noqa: BLE001
            ixbrl, formats, ixbrl_kinds = {}, {}, {}

        total_numeric_facts_ixbrlparse += sum(1 for k in ixbrl_kinds.values() if k == "numeric")

        ours_keys, ixbrl_keys = set(ours), set(ixbrl)
        shared = ours_keys & ixbrl_keys

        for key in shared:
            if values_equal(ours[key], ixbrl[key]):
                continue
            reason = mismatch_reason(ours[key], ixbrl[key], formats.get(key))
            if reason != "nested_fact":
                continue
            kind = ixbrl_kinds.get(key) or ours_kinds.get(key) or "unknown"
            vm_by_kind[kind] += 1
            if kind == "numeric":
                vm_concepts_numeric[key.concept] += 1
            else:
                vm_concepts_nonnumeric[key.concept] += 1
            if key.concept in wide_concepts and len(wide_concept_hits) < 20:
                wide_concept_hits.append(
                    {
                        "category": "value_mismatch",
                        "concept": key.concept,
                        "kind": kind,
                        "member": member,
                        "ours": ours[key],
                        "ixbrlparse": ixbrl[key],
                    }
                )

        for key in ixbrl_keys - ours_keys:
            reason = categorise_missing(key, path, data, is_xml)
            if reason != "nested_fact":
                continue
            kind = ixbrl_kinds.get(key, "unknown")
            io_by_kind[kind] += 1
            if kind == "numeric":
                io_concepts_numeric[key.concept] += 1
            else:
                io_concepts_nonnumeric[key.concept] += 1
            if key.concept in wide_concepts and len(wide_concept_hits) < 20:
                wide_concept_hits.append(
                    {
                        "category": "ixbrlparse_only",
                        "concept": key.concept,
                        "kind": kind,
                        "member": member,
                        "ixbrlparse": ixbrl[key],
                    }
                )

        n_processed += 1
        if n_processed % 1000 == 0:
            print(f"  ... {n_processed}/{len(paths)} files processed", flush=True)

    total_numeric_nested_losses = vm_by_kind.get("numeric", 0) + io_by_kind.get("numeric", 0)
    rate = (
        total_numeric_nested_losses / total_numeric_facts_ixbrlparse
        if total_numeric_facts_ixbrlparse
        else 0.0
    )
    any_wide_concept_affected = bool(wide_concept_hits)
    material = rate > 0.001 or any_wide_concept_affected

    result = {
        "value_mismatch_nested_fact_by_kind": dict(vm_by_kind),
        "value_mismatch_nested_fact_concepts_numeric": dict(
            vm_concepts_numeric.most_common(20)
        ),
        "value_mismatch_nested_fact_concepts_nonnumeric": dict(
            vm_concepts_nonnumeric.most_common(20)
        ),
        "ixbrlparse_only_nested_fact_by_kind": dict(io_by_kind),
        "ixbrlparse_only_nested_fact_concepts_numeric": dict(
            io_concepts_numeric.most_common(20)
        ),
        "ixbrlparse_only_nested_fact_concepts_nonnumeric": dict(
            io_concepts_nonnumeric.most_common(20)
        ),
        "total_numeric_facts_ixbrlparse_denominator": total_numeric_facts_ixbrlparse,
        "total_numeric_nested_fact_losses": total_numeric_nested_losses,
        "numeric_loss_rate": round(rate, 6),
        "wide_concept_hits": wide_concept_hits,
        "any_wide_concept_affected": any_wide_concept_affected,
        "decision_threshold": "rate > 0.1% OR any WIDE concept affected",
        "material_per_threshold": material,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "nested_fact_precheck.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"written: {out_path}")
    print(json.dumps({k: v for k, v in result.items() if k != "wide_concept_hits"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
