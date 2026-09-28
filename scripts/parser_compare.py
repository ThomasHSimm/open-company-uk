"""Phase 4 of the accounts-parser check: fact-level ours-vs-ixbrlparse comparison.

Not timed — a separate, correctness-only pass over the SAME fixed 5,000-file subset Phase 3
benchmarks (data/accounts/parser-benchmark-subset.json), so the same files ground both the
speed/memory numbers and the accuracy/completeness numbers. Re-parses rather than reusing
Phase 3's timed-run output, keeping the timed passes uncontaminated by comparison overhead.

Fact key: (company, source_member, concept, period_end, dimension_members) where
dimension_members is a sorted tuple of (dimension, member) local-name pairs — empty for a
non-dimensional fact, one pair for single-member, 2+ for multi-member (which ours never
produces, since core.py skips multi-member contexts entirely by design).

Usage:
    python scripts/parser_compare.py --census-dir data/accounts/parser-census
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pyarrow.parquet as pq  # noqa: E402

from ukcompany.accounts.core import NIL_RAW_VALUES, extract_filing  # noqa: E402

SUBSET_PATH = Path("data/accounts/parser-benchmark-subset.json")
CENSUS_DIR = Path("data/accounts/parser-census")
RESULTS_DIR = Path("data/accounts/parser-compare-results")

MEMBER_RE = re.compile(r"^Prod\d+_\d{4}_([^_]+)_(\d{8})\.(html|htm|xml)$", re.I)
CONTINUEDAT_RE = re.compile(rb'continuedAt\s*=\s*["\']([^"\']+)["\']', re.I)

# ixbrlparse's format-transform class names (ixbrlparse.components.formats) for the two
# formats ours cannot read correctly: `ixtNumComma` is comma-as-decimal-separator (ours'
# normalise_number strips commas as thousands separators unconditionally, so this misreads
# the magnitude by a power of ten), `ixtNumWordsEn` is numbers spelled out as words ("one
# hundred"), which fails Decimal() parsing entirely and returns None.
KNOWN_UNSUPPORTED_FORMATS = {"ixtNumComma", "ixtNumWordsEn"}


@dataclass(frozen=True)
class FactKey:
    company: str
    source_member: str
    concept: str
    period_end: str
    dimension_members: tuple[tuple[str, str], ...]


def local(qname: str | None) -> str:
    if not qname:
        return ""
    return qname.rsplit(":", 1)[-1].rsplit("}", 1)[-1]


def ours_facts(data: bytes, company: str, made_up_to_date: str, member: str) -> dict[FactKey, str]:
    filing = extract_filing(data, company, made_up_to_date)
    facts: dict[FactKey, str] = {}
    for obs in filing.observations:
        dims = ((obs.dimension, obs.member),) if obs.dimension else ()
        key = FactKey(company, member, obs.concept, obs.period_end, dims)
        value = obs.numeric_value if obs.numeric_value is not None else obs.raw_value
        facts[key] = value
    return facts


def ixbrlparse_facts(data: bytes, company: str, member: str) -> tuple[dict[FactKey, str], dict[FactKey, str]]:
    """Returns (facts, formats) — formats maps the same keys to their format attribute
    (transformation-registry name), where present, for later "why did this disagree" work."""
    import io

    from ixbrlparse import IXBRL

    result = IXBRL(io.StringIO(data.decode("utf-8", errors="replace")))
    facts: dict[FactKey, str] = {}
    formats: dict[FactKey, str] = {}
    for fact in result.numeric + result.nonnumeric:
        ctx = fact.context
        period_end = str(ctx.instant or ctx.enddate or "")
        segments = ctx.segments or []
        dims = tuple(
            sorted((local(seg.get("dimension")), local(seg.get("value"))) for seg in segments)
        )
        key = FactKey(company, member, local(fact.name), period_end, dims)
        facts[key] = str(fact.value) if fact.value is not None else ""
        fmt = getattr(fact, "format", None)
        if fmt is not None:
            fmt_name = type(fmt).__name__
            formats[key] = fmt_name
    return facts, formats


_FACT_TAG_EVENT_RE = re.compile(
    rb"<\s*(/?)\s*(?:[\w.-]+:)?(nonFraction|nonNumeric)\b([^>]*?)(/?)\s*>", re.I
)


def _has_nested_fact(data: bytes) -> bool:
    """Document-level check, reusing scripts/parser_census.py's stack-based approach: does
    ANY nonFraction/nonNumeric element in this document sit inside another one? Confirmed
    live: a fact nested this way (e.g. `business:BalanceSheetDate` nested inside another
    nonNumeric fact) is not just mis-valued but MISSING ENTIRELY from ours' output — the
    non-greedy closing-tag match on the outer element consumes the inner element's own
    opening tag as part of the outer's "body" and then stops at the inner's closing tag,
    so the inner fact's own opening tag never gets a chance to start a fresh regex match."""
    depth = 0
    for m in _FACT_TAG_EVENT_RE.finditer(data):
        closing = m.group(1) == b"/"
        if closing:
            depth = max(depth - 1, 0)
            continue
        if depth > 0:
            return True
        if m.group(4) != b"/":
            depth += 1
    return False


def categorise_missing(
    key: FactKey, member_path: Path, data: bytes, is_xml: bool
) -> str:
    """Why a fact ixbrlparse found is absent from ours' output."""
    if is_xml:
        return "xml"
    if len(key.dimension_members) >= 2:
        return "multi-member"
    # A typed-member context never survives into ours' output either (skipped_typed), but
    # by the time we're here we only know ours DIDN'T produce this key — distinguishing
    # "typed" from "other" requires checking the source for a typedMember on this context,
    # which core.extract_contexts already knows how to find.
    from ukcompany.accounts.core import ContextKind, extract_contexts

    contexts, _ = extract_contexts(data)
    for ctx in contexts.values():
        if ctx.period_end == key.period_end and ctx.kind == ContextKind.TYPED:
            return "typed"
    if CONTINUEDAT_RE.search(data):
        return "continuation"
    if _has_nested_fact(data):
        return "nested_fact"
    return "other"


_WHITESPACE_RE = re.compile(r"\s+")


def _collapse_whitespace(value: str) -> str:
    # ours' text_content() converts nbsp to a regular space but does not collapse runs of
    # whitespace; ixbrlparse keeps nbsp (\xa0) verbatim. Collapsing all whitespace to single
    # regular spaces for THIS comparison only (not touching core.py's own behaviour) treats
    # "R J  Case-Green" and "R J\xa0\xa0Case-Green" as the same text, which they are.
    return _WHITESPACE_RE.sub(" ", value).strip()


def _strip_all_whitespace(value: str) -> str:
    # ours' TAG_RE.sub() preserves whatever whitespace/newlines sat between source HTML
    # tags (e.g. "...loss.\r\n\r\nGrant recognition..." when a filing's <p> tags are on
    # separate lines); ixbrlparse's tree-based text extraction concatenates text from
    # separate block-level elements with NO separator at all ("...loss.Grant
    # recognition..."). Neither is wrong — they're different HTML-to-text conventions for
    # the same underlying narrative — so stripping ALL whitespace is the fallback check
    # for "is this actually the same text once formatting artifacts are removed".
    return _WHITESPACE_RE.sub("", value)


def values_equal(ours_value: str, ixbrl_value: str) -> bool:
    """Numeric-aware, whitespace-tolerant equality — ours stores numeric_value as a plain
    decimal string ("12000"), ixbrlparse's value is always a Python float ("12000.0" once
    stringified), so exact string equality would flag every whole-number fact as a false
    disagreement; likewise for nbsp-vs-space-only and inter-paragraph-separator-only
    differences in text facts."""
    if ours_value == ixbrl_value:
        return True
    try:
        return Decimal(ours_value) == Decimal(ixbrl_value)
    except InvalidOperation:
        pass
    if _collapse_whitespace(ours_value) == _collapse_whitespace(ixbrl_value):
        return True
    return _strip_all_whitespace(ours_value) == _strip_all_whitespace(ixbrl_value)


def mismatch_reason(ours_value: str, ixbrl_value: str, fmt: str | None) -> str:
    if ours_value in NIL_RAW_VALUES:
        # A deliberate Stage 1 design choice (see core.py's NIL_RAW_VALUES comment): a bare
        # dash is kept as "no value" at extraction time and only resolved to 0 downstream,
        # at pivot time — not a parsing gap, so it gets its own category rather than
        # "format" (misread) or "other" (unexplained).
        return "nil_dash_deferred_to_pivot"
    if fmt in KNOWN_UNSUPPORTED_FORMATS:
        return "format"
    # ours never follows ix:continuation chains — text_content() only ever sees the first
    # fragment, so for a truncated non-numeric fact ours' value is a true prefix of
    # ixbrlparse's longer, continuation-reconstructed text. Compared whitespace-collapsed:
    # source HTML routinely puts an nbsp right at the fragment boundary, which ours renders
    # as a plain space and ixbrlparse leaves as \xa0 — a real continuation, not a text
    # difference, so a raw-string prefix test misses it.
    ours_collapsed = _collapse_whitespace(ours_value)
    ixbrl_collapsed = _collapse_whitespace(ixbrl_value)
    if len(ixbrl_collapsed) > len(ours_collapsed) and ixbrl_collapsed.startswith(ours_collapsed):
        return "continuation"
    # The reverse direction: ours' value is LONGER and ends with ixbrlparse's shorter value
    # (e.g. ours: "...financial statements.true", ixbrlparse: "true"). This is the
    # documented nested-fact defect (docs/accounts-limitations.md's "a non-greedy
    # ix:nonNumeric match truncates when a same-named element is nested inside it") in its
    # other guise: an inner fact's text gets absorbed into an outer fact of the same
    # concept/context, so ours' single row conflates both instead of ixbrlparse's clean
    # separate one.
    if len(ours_collapsed) > len(ixbrl_collapsed) and ours_collapsed.endswith(ixbrl_collapsed):
        return "nested_fact"
    if fmt is not None:
        # ours never applies iXBRL Transformation Registry rules to non-numeric facts — it
        # keeps the raw displayed text as-is (docs/accounts-limitations.md: "kept in full
        # rather than pruned"), e.g. "3 January 2023" instead of ixbrlparse's normalised
        # "2023-01-03". Both are faithful representations of the same value in a different
        # format — not a parsing error, but a real, systematic difference worth naming.
        return "text_format_untransformed"
    return "other"


def wilson_ci(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion — well-behaved at the extremes (0%/100%)
    where a normal approximation gives nonsensical bounds outside [0, 1]."""
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denom = 1 + z**2 / total
    centre = p + z**2 / (2 * total)
    spread = z * ((p * (1 - p) / total + z**2 / (4 * total**2)) ** 0.5)
    return ((centre - spread) / denom, (centre + spread) / denom)


def load_year_lookup(census_dir: Path) -> dict[str, int]:
    lookup: dict[str, int] = {}
    for path in sorted(census_dir.glob("*.parquet")):
        table = pq.read_table(path, columns=["source_member", "archive_year"])
        for member, year in zip(
            table.column("source_member").to_pylist(),
            table.column("archive_year").to_pylist(),
            strict=True,
        ):
            lookup[member] = year
    return lookup


def compare_all(sample_paths: list[str], year_lookup: dict[str, int]) -> dict:
    per_year: dict[int, dict] = defaultdict(
        lambda: {
            "shared": 0,
            "agree": 0,
            "value_mismatches": Counter(),
            "ixbrlparse_only": Counter(),
            "ours_only": 0,
            "examples": defaultdict(list),
        }
    )
    disagreeing_members: set[str] = set()

    for path_str in sample_paths:
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
            ours = ours_facts(data, company, made_up_to_date, member) if not is_xml else {}
        except Exception:  # noqa: BLE001
            ours = {}
        try:
            ixbrl, formats = ixbrlparse_facts(data, company, member)
        except Exception:  # noqa: BLE001
            ixbrl, formats = {}, {}

        bucket = per_year[year]
        ours_keys, ixbrl_keys = set(ours), set(ixbrl)
        shared = ours_keys & ixbrl_keys
        bucket["shared"] += len(shared)
        file_disagreed = False
        for key in shared:
            if values_equal(ours[key], ixbrl[key]):
                bucket["agree"] += 1
            else:
                file_disagreed = True
                # Distinct from ixbrlparse_only below: both parsers found this fact, they
                # just disagree on its value.
                reason = mismatch_reason(ours[key], ixbrl[key], formats.get(key))
                bucket["value_mismatches"][reason] += 1
                example_bucket = f"value_mismatch_{reason}"
                if len(bucket["examples"][example_bucket]) < 10:
                    bucket["examples"][example_bucket].append(
                        {
                            "key": str(key),
                            "ours": ours[key],
                            "ixbrlparse": ixbrl[key],
                            "format": formats.get(key),
                        }
                    )

        for key in ixbrl_keys - ours_keys:
            reason = categorise_missing(key, path, data, is_xml)
            bucket["ixbrlparse_only"][reason] += 1
            file_disagreed = True
            if len(bucket["examples"][f"ixbrlparse_only_{reason}"]) < 5:
                bucket["examples"][f"ixbrlparse_only_{reason}"].append(str(key))

        n_ours_only = len(ours_keys - ixbrl_keys)
        bucket["ours_only"] += n_ours_only
        if n_ours_only:
            file_disagreed = True

        if file_disagreed:
            disagreeing_members.add(member)

    report = {}
    for year, bucket in sorted(per_year.items()):
        shared = bucket["shared"]
        agree = bucket["agree"]
        lo, hi = wilson_ci(agree, shared)
        report[year] = {
            "shared_facts": shared,
            "agreement": agree,
            "agreement_rate": round(agree / shared, 4) if shared else None,
            "agreement_ci95": [round(lo, 4), round(hi, 4)],
            "value_mismatches_by_reason": dict(bucket["value_mismatches"]),
            "ixbrlparse_only_total": sum(bucket["ixbrlparse_only"].values()),
            "ixbrlparse_only_by_reason": dict(bucket["ixbrlparse_only"]),
            "ours_only_total": bucket["ours_only"],
            "examples": {k: v for k, v in bucket["examples"].items()},
        }
    return {"by_year": report, "disagreeing_members": sorted(disagreeing_members)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census-dir", type=Path, default=CENSUS_DIR)
    parser.add_argument("--subset", type=Path, default=SUBSET_PATH)
    args = parser.parse_args()

    subset = json.loads(args.subset.read_text(encoding="utf-8"))
    paths = subset["timed"]
    year_lookup = load_year_lookup(args.census_dir)
    print(f"comparing {len(paths)} files across {len(set(year_lookup.values()))} years")

    result = compare_all(paths, year_lookup)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "ours_vs_ixbrlparse.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"written: {out_path}")
    for year, stats in sorted(result["by_year"].items()):
        print(
            year,
            f"agreement={stats['agreement_rate']}",
            f"ci95={stats['agreement_ci95']}",
            f"ixbrlparse_only={stats['ixbrlparse_only_by_reason']}",
            f"ours_only={stats['ours_only_total']}",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
