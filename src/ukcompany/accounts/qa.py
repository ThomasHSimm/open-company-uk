"""Read-only data-quality summaries for the accounts LONG table."""

from __future__ import annotations

import glob as glob_module
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .core import EMPLOYEE_CONCEPT, TARGET_CONCEPTS
from .pivot import require_polars, to_lazy, track_peak_rss

SOURCE_KEYS = (
    "company",
    "period_end",
    "concept",
    "source_year",
    "source_month",
    "source_archive",
    "source_member",
)

def selected_target_facts(long_frame):
    """Return a LazyFrame filtered to target concepts (and `selected` status if present).

    Accepts an eager DataFrame or a LazyFrame; callers that need an eager result collect
    at their own boundary (see `member_histogram`, `total_component_reconciliation`) so the
    full corpus is never materialised before this filter narrows it to ~9 concepts.
    """
    pl = require_polars()
    lazy = to_lazy(long_frame)
    selected = lazy.filter(pl.col("concept").is_in(TARGET_CONCEPTS))
    if "status" in lazy.collect_schema().names():
        selected = selected.filter(pl.col("status") == "selected")
    return selected


def _iter_monthly_paths(parts: str | Path) -> list[str]:
    paths = sorted(glob_module.glob(str(parts)))
    if not paths:
        raise ValueError(f"no Parquet files match: {parts}")
    return paths


@dataclass(frozen=True)
class RestatementRateResult:
    """Month-ordered running-tally restatement rate — Decision 6, continuous ranges only.

    Matches the panel check's definition (`docs/panel-check.md`'s 7.94%): non-dimensional
    (`dimension IS NULL`), `status == 'selected'` numeric facts for the nine target
    concepts, keyed by (company, period_end, concept). A key is "repeated" once it appears
    in a second filing; "disagree" means a later filing reports a different
    scale-normalised value than the first one seen.

    Computed as a running tally over archives ordered oldest to newest, not a global
    self-join/group-by: that group-by's key cardinality approaches the row count (tested
    and measured to exceed 25 GB even isolated from other work — see AUDIT.md). A gap
    between archives makes "restated later" indistinguishable from "not resampled", so
    `scope_label` must name the exact continuous range used and this must never be
    aggregated with the lone gap-separated months.
    """

    scope_label: str
    keys_total: int
    keys_repeated: int
    keys_disagree: int
    by_concept: tuple[tuple[str, int, int], ...]

    @property
    def disagreement_rate(self) -> float:
        return self.keys_disagree / self.keys_repeated if self.keys_repeated else 0.0


def restatement_rate_over_parts(parts: str | Path, *, scope_label: str) -> RestatementRateResult:
    """Running tally of first-seen values per (company, period_end, concept) key.

    Processes one archive at a time in chronological order (the `accounts-long-YYYY-MM`
    filename sort is already chronological), so the only state held across the whole run is
    the dict of distinct keys seen so far — proportional to key cardinality (tens of
    millions, a few GB), not to the raw fact-row count.
    """
    pl = require_polars()
    first_value: dict[tuple[str, str, str], str] = {}
    repeated: set[tuple[str, str, str]] = set()
    disagree: set[tuple[str, str, str]] = set()

    for path in _iter_monthly_paths(parts):
        frame = (
            pl.scan_parquet(path)
            .filter(
                pl.col("concept").is_in(TARGET_CONCEPTS)
                & (pl.col("status") == "selected")
                & pl.col("dimension").is_null()
                & pl.col("numeric_value").is_not_null()
            )
            .select("company", "period_end", "concept", "numeric_value")
            .collect(engine="streaming")
        )
        for company, period_end, concept, value in frame.iter_rows():
            key = (company, period_end, sys.intern(concept))
            prior = first_value.get(key)
            if prior is None:
                first_value[key] = value
            else:
                repeated.add(key)
                if value != prior:
                    disagree.add(key)

    repeated_by_concept: Counter[str] = Counter(key[2] for key in repeated)
    disagree_by_concept: Counter[str] = Counter(key[2] for key in disagree)
    by_concept = tuple(
        (concept, repeated_by_concept.get(concept, 0), disagree_by_concept.get(concept, 0))
        for concept in sorted(TARGET_CONCEPTS)
    )
    return RestatementRateResult(
        scope_label=scope_label,
        keys_total=len(first_value),
        keys_repeated=len(repeated),
        keys_disagree=len(disagree),
        by_concept=by_concept,
    )


def render_restatement_rate_report(result: RestatementRateResult) -> str:
    lines = [
        "# Accounts restatement rate (month-ordered running tally)",
        "",
        f"Scope: **{result.scope_label}** (continuous months only — a gap between archives "
        'makes "restated later" indistinguishable from "not resampled"; never aggregate '
        "this with the lone gap-separated months).",
        "",
        "Same definition as the panel check (`docs/panel-check.md`'s 7.94%): "
        "non-dimensional (`dimension IS NULL`), `status == 'selected'` numeric facts for "
        "the nine target concepts, keyed by (company, period_end, concept). \"Repeated\" "
        "means the key appears in >=2 filings within scope; \"disagree\" means a later "
        "filing reports a different scale-normalised value than the first one seen.",
        "",
        f"- Distinct keys: {result.keys_total:,}",
        f"- Repeated keys: {result.keys_repeated:,}",
        f"- Disagree: {result.keys_disagree:,} ({result.disagreement_rate:.2%} of repeated)",
        "",
        "## By concept",
        "",
        "| Concept | Repeated keys | Exact match | Disagree |",
        "|---|---:|---:|---:|",
    ]
    for concept, concept_repeated, concept_disagree in result.by_concept:
        exact = concept_repeated - concept_disagree
        exact_rate = exact / concept_repeated if concept_repeated else 0.0
        disagree_rate = concept_disagree / concept_repeated if concept_repeated else 0.0
        lines.append(
            f"| `{concept}` | {concept_repeated:,} | {exact:,} ({exact_rate:.2%}) | "
            f"{concept_disagree:,} ({disagree_rate:.2%}) |"
        )
    lines.append("")
    return "\n".join(lines)


def member_histogram_over_parts(parts: str | Path):
    """Memory-bounded histogram: two aggregation levels, computed per file.

    All 9 target concepts across every dimensional member measured 113M rows / ~16.6 GB for
    the full corpus (bigger than pivot's mapped-cell slice, since QA keeps every currency
    and every member, not just the WIDE-mapped ones), which is too large to group by
    (concept, dimension, member) in one pass. `observations` is a plain row count, so
    per-file partial sums combine exactly. `companies`/`company_periods` are `n_unique` and
    do NOT compose by summing per-file counts (the same company files across many months),
    so they are computed from a separate, column-projected distinct-tuple table instead of
    the full fact rows.
    """
    pl = require_polars()
    partial_counts = []
    distinct_tuples = []
    for path in _iter_monthly_paths(parts):
        dimensional = selected_target_facts(pl.scan_parquet(path)).filter(
            pl.col("dimension").is_not_null()
        )
        partial_counts.append(
            dimensional.group_by("concept", "dimension", "member")
            .agg(pl.len().alias("n"))
            .collect(engine="streaming")
        )
        distinct_tuples.append(
            dimensional.select("concept", "dimension", "member", "company", "period_end")
            .unique()
            .collect(engine="streaming")
        )
    observations = (
        pl.concat(partial_counts, how="vertical")
        .lazy()
        .group_by("concept", "dimension", "member")
        .agg(pl.col("n").sum().alias("observations"))
    )
    company_stats = (
        pl.concat(distinct_tuples, how="vertical")
        .lazy()
        .group_by("concept", "dimension", "member")
        .agg(
            pl.col("company").n_unique().alias("companies"),
            pl.struct("company", "period_end").n_unique().alias("company_periods"),
        )
    )
    return (
        observations.join(company_stats, on=["concept", "dimension", "member"], how="inner")
        .sort("concept", "observations", descending=[False, True])
        .collect(engine="streaming")
    )


def total_component_reconciliation_over_parts(parts: str | Path, relative_tolerance: float = 1e-6):
    """Memory-bounded reconciliation: the expensive group-by/join is computed per file.

    `SOURCE_KEYS` includes `source_archive`, so a total can only join to a component from
    the *same* source archive — the join can never match across files. Each file's small
    `comparisons` result is collected before the next file is scanned, and only the small
    per-file results (not the full fact rows) are concatenated for the final summary.
    """
    pl = require_polars()
    per_file_comparisons = []
    for path in _iter_monthly_paths(parts):
        numeric = selected_target_facts(pl.scan_parquet(path)).filter(
            pl.col("numeric_value").is_not_null()
            & ((pl.col("currency") == "GBP") | (pl.col("concept") == EMPLOYEE_CONCEPT))
        ).with_columns(pl.col("numeric_value").cast(pl.Float64, strict=False).alias("value"))
        totals = (
            numeric.filter(pl.col("dimension").is_null())
            .group_by(*SOURCE_KEYS)
            .agg(pl.col("value").first().alias("total"))
        )
        components = (
            numeric.filter(pl.col("dimension").is_not_null())
            .group_by(*SOURCE_KEYS, "dimension")
            .agg(
                pl.col("value").sum().alias("component_sum"),
                pl.len().alias("n_members"),
            )
        )
        comparisons = totals.join(components, on=list(SOURCE_KEYS), how="inner").with_columns(
            (pl.col("total") - pl.col("component_sum")).abs().alias("absolute_difference")
        )
        per_file_comparisons.append(comparisons.collect(engine="streaming"))
    all_comparisons = pl.concat(per_file_comparisons, how="vertical").with_columns(
        (
            pl.col("absolute_difference")
            <= pl.max_horizontal(pl.lit(1.0), pl.col("total").abs() * relative_tolerance)
        ).alias("agrees")
    )
    summary = (
        all_comparisons.lazy()
        .group_by("concept")
        .agg(
            pl.len().alias("comparisons"),
            pl.col("agrees").sum().alias("agreements"),
            pl.col("absolute_difference").median().alias("median_absolute_difference"),
        )
        .with_columns((pl.col("agreements") / pl.col("comparisons")).alias("agreement_rate"))
        .sort("concept")
        .collect(engine="streaming")
    )
    sorted_comparisons = all_comparisons.sort(
        "concept", "absolute_difference", descending=[False, True]
    )
    return summary, sorted_comparisons


def member_histogram(long_frame):
    pl = require_polars()
    return (
        selected_target_facts(long_frame)
        .filter(pl.col("dimension").is_not_null())
        .group_by("concept", "dimension", "member")
        .agg(
            pl.len().alias("observations"),
            pl.col("company").n_unique().alias("companies"),
            pl.struct("company", "period_end").n_unique().alias("company_periods"),
        )
        .sort("concept", "observations", descending=[False, True])
        .collect(engine="streaming")
    )


def total_component_reconciliation(long_frame, relative_tolerance: float = 1e-6):
    """Compare reported totals with member sums within the same source filing."""
    pl = require_polars()
    numeric = selected_target_facts(long_frame).filter(
        pl.col("numeric_value").is_not_null()
        & ((pl.col("currency") == "GBP") | (pl.col("concept") == EMPLOYEE_CONCEPT))
    ).with_columns(pl.col("numeric_value").cast(pl.Float64, strict=False).alias("value"))
    totals = (
        numeric.filter(pl.col("dimension").is_null())
        .group_by(*SOURCE_KEYS)
        .agg(pl.col("value").first().alias("total"))
    )
    components = (
        numeric.filter(pl.col("dimension").is_not_null())
        .group_by(*SOURCE_KEYS, "dimension")
        .agg(
            pl.col("value").sum().alias("component_sum"),
            pl.len().alias("n_members"),
        )
    )
    comparisons = totals.join(components, on=list(SOURCE_KEYS), how="inner").with_columns(
        (pl.col("total") - pl.col("component_sum")).abs().alias("absolute_difference")
    )
    comparisons = comparisons.with_columns(
        (
            pl.col("absolute_difference")
            <= pl.max_horizontal(
                pl.lit(1.0),
                pl.col("total").abs() * relative_tolerance,
            )
        ).alias("agrees")
    )
    summary = (
        comparisons.group_by("concept")
        .agg(
            pl.len().alias("comparisons"),
            pl.col("agrees").sum().alias("agreements"),
            pl.col("absolute_difference").median().alias("median_absolute_difference"),
        )
        .with_columns(
            (pl.col("agreements") / pl.col("comparisons")).alias("agreement_rate")
        )
        .sort("concept")
    )
    materialised_summary, materialised_comparisons = pl.collect_all(
        [summary, comparisons.sort("concept", "absolute_difference", descending=[False, True])],
        engine="streaming",
    )
    return materialised_summary, materialised_comparisons


def render_qa_report(histogram, reconciliation, *, source: str) -> str:
    lines = [
        "# Accounts member and reconciliation QA",
        "",
        f"Source LONG table: `{source}`.",
        "",
        "## Total versus component sums",
        "",
        "This is diagnostic only. No reported value is corrected or replaced. Agreement uses an absolute tolerance of max(£1, 1e-6 × |total|). Components are summed only within the same dimension and source filing; parallel dimensional axes are never combined.",
        "",
        "| Concept | Comparisons | Agreements | Agreement rate | Median absolute difference |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in reconciliation.iter_rows(named=True):
        lines.append(
            f"| `{row['concept']}` | {row['comparisons']:,} | {row['agreements']:,} | "
            f"{row['agreement_rate']:.1%} | {row['median_absolute_difference']:,.2f} |"
        )
    if reconciliation.is_empty():
        lines.append("| _No comparable totals and members_ | 0 | 0 | n/a | n/a |")
    lines.extend(
        [
            "",
            "## Member-frequency histogram",
            "",
            "All target concepts are included. Frequencies count only Stage 1 observations tagged `selected`; conflict rows remain in the archive for a Stage 2 policy. This table is the evidence for a human-selected WIDE member map.",
            "",
            "| Concept | Dimension | Member | Observations | Companies | Company-periods |",
            "|---|---|---|---:|---:|---:|",
        ]
    )
    for row in histogram.iter_rows(named=True):
        lines.append(
            f"| `{row['concept']}` | `{row['dimension']}` | `{row['member']}` | "
            f"{row['observations']:,} | {row['companies']:,} | {row['company_periods']:,} |"
        )
    lines.extend(
        [
            "",
            "## Required human decisions",
            "",
            "- Select the final WIDE member column map from the histogram; no map is inferred here.",
            "- Decide whether `PropertyPlantEquipment` members should be promoted to WIDE.",
            "- Run reconnaissance around 2010, 2013, and 2016 before choosing an effective historical start year.",
            "- Approve the Kaggle framing and OGL v3.0 attribution wording before publication.",
            "",
            "## Draft Kaggle licensing and framing note — human approval required",
            "",
            "Contains public Companies House accounts data used under the Open Government Licence v3.0. This derivative contains financial facts only, is not a complete representation of a company or its financial position, and retains documented coverage, filing-format, dimensional, currency, and restatement limitations. Companies House and the UK Government do not endorse this derivative.",
            "",
            "## Limitations",
            "",
            "- Pre-2019 archive behavior is not yet validated.",
            "- Non-GBP monetary observations remain in LONG but are excluded from WIDE; no currency conversion is performed.",
            "- Scale handling is synthetically tested, but real recon samples contained only missing or zero scale.",
            "- Employee-count coverage has a 2019–2021 reporting-regime break and must not be treated as company signal.",
            "- Equity missingness varies non-randomly by month.",
            "- Predictive publication must use `as_first_reported`; `latest` incorporates later comparative restatements.",
            "- Genuine Creditors totals are only about 4% in the two-archive sample because Creditors are dimensionally dominant. Null total does not imply an absent filing; users should rely on explicitly curated member columns.",
            "- Run the random regex-versus-lxml parser-agreement audit before starting a full-history extraction.",
            "",
        ]
    )
    return "\n".join(lines)


def write_qa(
    long_path: str | Path,
    histogram_output: str | Path,
    reconciliation_output: str | Path,
    report_output: str | Path,
) -> int:
    """Write the QA report; returns peak RSS in bytes for this run.

    Processes one monthly Parquet at a time (see `member_histogram_over_parts`,
    `total_component_reconciliation_over_parts`) so peak memory never scales with the full
    multi-month corpus.
    """
    with track_peak_rss() as peak:
        histogram = member_histogram_over_parts(long_path)
        reconciliation, _comparisons = total_component_reconciliation_over_parts(long_path)
        for output in (histogram_output, reconciliation_output, report_output):
            Path(output).parent.mkdir(parents=True, exist_ok=True)
        histogram.write_csv(histogram_output)
        reconciliation.write_csv(reconciliation_output)
        Path(report_output).write_text(
            render_qa_report(histogram, reconciliation, source=Path(long_path).name),
            encoding="utf-8",
        )
    return peak()
