"""Phase A of the v2 parser-fix build: analysis only, no code changes to the parser.

Reuses the existing Phase 4 comparison machinery (scripts/parser_compare.py) completely
unmodified — same fixed 5,000-file subset, same FactKey shape, same mismatch_reason/
categorise_missing categorisation — and adds three new, narrower questions on top of it:

  A1. Restrict the comparison to exactly the concepts/members config/accounts-wide-columns.json
      turns into WIDE columns: does the parser's known gaps actually touch the columns that
      get published, and by how much?
  A2. Numeric-only agreement rate, excluding nil_dash_deferred_to_pivot (a deliberate design
      choice, not a disagreement) — the accuracy figure that matters for WIDE, since WIDE only
      ever holds numeric cells (except AverageNumberEmployeesDuringPeriod, which is numeric
      too) plus the fact-of-a-value in the employee count.
  A3. Which typed-member dimensions appear, with counts, and what their member VALUES look
      like structurally (name-shaped / free-text-shaped / code-shaped) — without ever printing
      a value classified as name-shaped. This is descriptive, not a scoping decision — output
      feeds a future call on whether typed members could ever be safely captured, and this
      script does not make that call.

Usage:
    python scripts/phase_a_analysis.py
"""

from __future__ import annotations

import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from parser_compare import (  # noqa: E402
    CENSUS_DIR,
    MEMBER_RE,
    SUBSET_PATH,
    FactKey,
    categorise_missing,
    load_year_lookup,
    local,
    mismatch_reason,
    values_equal,
)

from ukcompany.accounts.core import extract_filing  # noqa: E402

RESULTS_DIR = Path("data/accounts/parser-compare-results")
WIDE_COLUMNS_CONFIG = Path("config/accounts-wide-columns.json")
EMPLOYEE_CONCEPT = "AverageNumberEmployeesDuringPeriod"


# --- fact-kind-aware extraction (parser_compare.py's ours_facts/ixbrlparse_facts discard
# numeric-vs-non-numeric once they've picked a display value; A2 needs to keep it, so these
# are separate, minimal wrappers rather than a change to parser_compare.py's existing,
# already-depended-on (by arelle_correctness.py) function signatures) ---


def ours_facts_with_kind(
    data: bytes, company: str, made_up_to_date: str, member: str
) -> tuple[dict[FactKey, str], dict[FactKey, str]]:
    filing = extract_filing(data, company, made_up_to_date)
    facts: dict[FactKey, str] = {}
    kinds: dict[FactKey, str] = {}
    for obs in filing.observations:
        dims = ((obs.dimension, obs.member),) if obs.dimension else ()
        key = FactKey(company, member, obs.concept, obs.period_end, dims)
        value = obs.numeric_value if obs.numeric_value is not None else obs.raw_value
        facts[key] = value
        kinds[key] = obs.fact_kind
    return facts, kinds


def ixbrlparse_facts_with_kind(
    data: bytes, company: str, member: str
) -> tuple[dict[FactKey, str], dict[FactKey, str], dict[FactKey, str]]:
    from ixbrlparse import IXBRL

    result = IXBRL(io.StringIO(data.decode("utf-8", errors="replace")))
    facts: dict[FactKey, str] = {}
    formats: dict[FactKey, str] = {}
    kinds: dict[FactKey, str] = {}
    for is_numeric, fact_list in ((True, result.numeric), (False, result.nonnumeric)):
        for fact in fact_list:
            ctx = fact.context
            period_end = str(ctx.instant or ctx.enddate or "")
            segments = ctx.segments or []
            dims = tuple(
                sorted((local(seg.get("dimension")), local(seg.get("value"))) for seg in segments)
            )
            key = FactKey(company, member, local(fact.name), period_end, dims)
            facts[key] = str(fact.value) if fact.value is not None else ""
            kinds[key] = "numeric" if is_numeric else "non-numeric"
            fmt = getattr(fact, "format", None)
            if fmt is not None:
                formats[key] = type(fmt).__name__
    return facts, formats, kinds


def load_wide_targets() -> dict[str, tuple[str, tuple[tuple[str, str], ...]]]:
    """Returns {column_label: (concept, dimension_members)} for all 13 WIDE columns."""
    config = json.loads(WIDE_COLUMNS_CONFIG.read_text(encoding="utf-8"))
    targets: dict[str, tuple[str, tuple[tuple[str, str], ...]]] = {}
    for concept in config["totals"]:
        targets[concept] = (concept, ())
    for member in config["members"]:
        targets[member["column"]] = (
            member["concept"],
            ((member["dimension"], member["member"]),),
        )
    return targets


def matches_target(key: FactKey, concept: str, dims: tuple[tuple[str, str], ...]) -> bool:
    return key.concept == concept and key.dimension_members == dims


# --- A3: typed-member dimension/value shape scan ---

TYPED_MEMBER_FULL_RE = re.compile(
    rb"<\s*(?:[\w.-]+:)?typedMember\b([^>]*)>(.*?)</\s*(?:[\w.-]+:)?typedMember\s*>",
    re.I | re.S,
)
# [\w.-]+ has no colon in its character class, so without the explicit optional-prefix
# group a qualified name like "frs-common:SomeElement" would only capture the PREFIX
# ("frs-common") as the tag, silently swallowing ":SomeElement" into the discarded
# attributes segment — the same prefix-vs-local-name trap this whole audit exists to catch
# elsewhere in the codebase. Matches core.py's `(?:[\w.-]+:)?name` idiom.
CHILD_ELEMENT_RE = re.compile(rb"<\s*((?:[\w.-]+:)?[\w.-]+)\b[^>]*>(.*?)</", re.S)
DIMENSION_ATTR_RE = re.compile(rb"""dimension\s*=\s*(['"])(.*?)\1""", re.I)

_NAME_SHAPE_RE = re.compile(r"^[A-Z][a-zA-Z'-]+(\s+[A-Z][a-zA-Z'.-]+){1,3}$")
_CODE_SHAPE_RE = re.compile(r"^[A-Za-z0-9._-]{1,20}$")


def classify_value_shape(value: str) -> str:
    value = value.strip()
    if not value:
        return "empty"
    if _NAME_SHAPE_RE.match(value) and " " in value and not any(c.isdigit() for c in value):
        return "name-shaped"
    if _CODE_SHAPE_RE.match(value) and " " not in value:
        return "code-shaped"
    if len(value) > 40 or value.count(" ") > 4:
        return "free-text-shaped"
    return "other-short-value"


def scan_typed_members(data: bytes) -> list[tuple[str, str, str]]:
    """Returns (dimension_local_name, typed_element_local_name, value_shape) for every
    typedMember found in this filing — never the raw value itself."""
    from ukcompany.accounts.core import local_name, parse_attrs, text_content

    results = []
    for raw_attrs, body in TYPED_MEMBER_FULL_RE.findall(data):
        dim_match = DIMENSION_ATTR_RE.search(raw_attrs)
        dimension = local_name(dim_match.group(2).decode("utf-8", "replace")) if dim_match else ""
        child = CHILD_ELEMENT_RE.search(body)
        if not child:
            continue
        element_name = local_name(child.group(1).decode("utf-8", "replace"))
        value = text_content(child.group(2))
        results.append((dimension, element_name, classify_value_shape(value)))
    _ = parse_attrs  # imported for symmetry with other core.py helpers; not used directly
    return results


def main() -> int:
    subset = json.loads(SUBSET_PATH.read_text(encoding="utf-8"))
    paths = subset["timed"]
    year_lookup = load_year_lookup(CENSUS_DIR)
    targets = load_wide_targets()

    # A1 accumulators: per column, shared/agree/mismatch-by-reason/ixbrlparse-only-by-reason/ours-only
    a1: dict[str, dict] = {
        col: {
            "shared": 0,
            "agree": 0,
            "value_mismatches": Counter(),
            "ixbrlparse_only": Counter(),
            "ours_only": 0,
        }
        for col in targets
    }
    employee_examples: list[dict] = []

    # A2 accumulators: per year, numeric-only shared/agree, EXCLUDING nil_dash_deferred_to_pivot
    a2: dict[int, dict] = defaultdict(lambda: {"shared": 0, "agree": 0, "excluded_nil_dash": 0})

    # A3 accumulator: (dimension, element_name) -> Counter(shape -> count)
    a3: dict[tuple[str, str], Counter] = defaultdict(Counter)

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

        ours_keys, ixbrl_keys = set(ours), set(ixbrl)
        shared = ours_keys & ixbrl_keys

        # --- A1 ---
        for key in shared:
            for col, (concept, dims) in targets.items():
                if not matches_target(key, concept, dims):
                    continue
                bucket = a1[col]
                bucket["shared"] += 1
                if values_equal(ours[key], ixbrl[key]):
                    bucket["agree"] += 1
                else:
                    reason = mismatch_reason(ours[key], ixbrl[key], formats.get(key))
                    bucket["value_mismatches"][reason] += 1
                    if concept == EMPLOYEE_CONCEPT and reason == "nested_fact" and len(
                        employee_examples
                    ) < 8:
                        employee_examples.append(
                            {
                                "key": str(key),
                                "ours": ours[key],
                                "ixbrlparse": ixbrl[key],
                            }
                        )
        for key in ixbrl_keys - ours_keys:
            for col, (concept, dims) in targets.items():
                if not matches_target(key, concept, dims):
                    continue
                reason = categorise_missing(key, path, data, is_xml)
                a1[col]["ixbrlparse_only"][reason] += 1
                if concept == EMPLOYEE_CONCEPT and reason == "nested_fact" and len(
                    employee_examples
                ) < 8:
                    employee_examples.append(
                        {"key": str(key), "ours": None, "ixbrlparse": ixbrl[key]}
                    )
        for key in ours_keys - ixbrl_keys:
            for col, (concept, dims) in targets.items():
                if matches_target(key, concept, dims):
                    a1[col]["ours_only"] += 1

        # --- A2 ---
        bucket2 = a2[year]
        for key in shared:
            kind = ixbrl_kinds.get(key) or ours_kinds.get(key)
            if kind != "numeric":
                continue
            if values_equal(ours[key], ixbrl[key]):
                bucket2["shared"] += 1
                bucket2["agree"] += 1
            else:
                reason = mismatch_reason(ours[key], ixbrl[key], formats.get(key))
                if reason == "nil_dash_deferred_to_pivot":
                    bucket2["excluded_nil_dash"] += 1
                else:
                    bucket2["shared"] += 1

        # --- A3 ---
        for dimension, element_name, shape in scan_typed_members(data):
            a3[(dimension, element_name)][shape] += 1

        n_processed += 1
        if n_processed % 1000 == 0:
            print(f"  ... {n_processed}/{len(paths)} files processed", flush=True)

    # --- write A1 ---
    a1_report = {}
    for col, bucket in a1.items():
        shared = bucket["shared"]
        a1_report[col] = {
            "shared_facts": shared,
            "agreement": bucket["agree"],
            "agreement_rate": round(bucket["agree"] / shared, 4) if shared else None,
            "value_mismatches_by_reason": dict(bucket["value_mismatches"]),
            "ixbrlparse_only_total": sum(bucket["ixbrlparse_only"].values()),
            "ixbrlparse_only_by_reason": dict(bucket["ixbrlparse_only"]),
            "ours_only_total": bucket["ours_only"],
        }

    # --- write A2 (with Wilson CI) ---
    from parser_compare import wilson_ci

    a2_report = {}
    for year, bucket in sorted(a2.items()):
        shared, agree = bucket["shared"], bucket["agree"]
        lo, hi = wilson_ci(agree, shared)
        a2_report[year] = {
            "numeric_shared_facts_excl_nil_dash": shared,
            "agreement": agree,
            "agreement_rate": round(agree / shared, 4) if shared else None,
            "agreement_ci95": [round(lo, 4), round(hi, 4)],
            "excluded_nil_dash_count": bucket["excluded_nil_dash"],
        }
    total_shared = sum(b["numeric_shared_facts_excl_nil_dash"] for b in a2_report.values())
    total_agree = sum(b["agreement"] for b in a2_report.values())
    lo, hi = wilson_ci(total_agree, total_shared)
    a2_report["ALL_YEARS"] = {
        "numeric_shared_facts_excl_nil_dash": total_shared,
        "agreement": total_agree,
        "agreement_rate": round(total_agree / total_shared, 4) if total_shared else None,
        "agreement_ci95": [round(lo, 4), round(hi, 4)],
    }

    # --- write A3 ---
    a3_report = []
    for (dimension, element_name), shapes in sorted(
        a3.items(), key=lambda item: -sum(item[1].values())
    ):
        total = sum(shapes.values())
        dominant_shape = shapes.most_common(1)[0][0]
        a3_report.append(
            {
                "dimension": dimension,
                "typed_element": element_name,
                "count": total,
                "shape_breakdown": dict(shapes),
                "dominant_shape": dominant_shape,
                "would_be_personal_data_if_captured": dominant_shape == "name-shaped",
            }
        )

    result = {
        "subset_size": len(paths),
        "files_processed": n_processed,
        "a1_wide_columns": a1_report,
        "a1_employee_nested_fact_examples": employee_examples,
        "a2_numeric_agreement_by_year": a2_report,
        "a3_typed_member_dimensions": a3_report,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "phase_a_analysis.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"written: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
