"""Read-only data-quality summaries for the accounts LONG table."""

from __future__ import annotations

from pathlib import Path

from .core import EMPLOYEE_CONCEPT
from .pivot import require_polars

SOURCE_KEYS = (
    "company",
    "period_end",
    "concept",
    "source_year",
    "source_month",
    "source_archive",
    "source_member",
)


def member_histogram(long_frame):
    pl = require_polars()
    return (
        long_frame.filter(pl.col("dimension").is_not_null())
        .group_by("concept", "dimension", "member")
        .agg(
            pl.len().alias("observations"),
            pl.col("company").n_unique().alias("companies"),
            pl.struct("company", "period_end").n_unique().alias("company_periods"),
        )
        .sort("concept", "observations", descending=[False, True])
    )


def total_component_reconciliation(long_frame, relative_tolerance: float = 1e-6):
    """Compare reported totals with member sums within the same source filing."""
    pl = require_polars()
    numeric = long_frame.filter(
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
    return summary, comparisons.sort("concept", "absolute_difference", descending=[False, True])


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
            "All target concepts are included. Frequencies count unreconciled LONG observations; this table is the evidence for a human-selected WIDE member map.",
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
) -> None:
    pl = require_polars()
    long_frame = pl.read_parquet(long_path)
    histogram = member_histogram(long_frame)
    reconciliation, _comparisons = total_component_reconciliation(long_frame)
    for output in (histogram_output, reconciliation_output, report_output):
        Path(output).parent.mkdir(parents=True, exist_ok=True)
    histogram.write_csv(histogram_output)
    reconciliation.write_csv(reconciliation_output)
    Path(report_output).write_text(
        render_qa_report(histogram, reconciliation, source=Path(long_path).name), encoding="utf-8"
    )
