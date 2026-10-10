"""Accounts-only historical case lead-time analysis.

The analysis is case-only and aggregate-only. Every accounts value is gated by its own
``as_first_reported`` provenance cell; ``row_available_yyyymm`` is never used.
"""

from __future__ import annotations

import hashlib
import json
import resource
import subprocess
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ukcompany.accounts.features import MAX_PRIOR_GAP_MONTHS, PLAUSIBLE_PERIOD_START
from ukcompany.accounts.pivot import require_polars
from ukcompany.psc.loader import _connect, _sql_literal

from .labels import LabelSet, load_labels

SUPPORTED_CASE_TYPES = (
    "administration",
    "compulsory_liquidation",
    "corporate_voluntary_arrangement",
    "creditors_voluntary_liquidation",
)
LEAD_MONTHS = (6, 12, 24)
CONVENTIONS = ("registration_month", "one_cycle_lag")
MIN_EVENT_MONTH = "2015-01"
MAX_EVENT_MONTH = "2024-04"

CELL_COLUMNS = {
    "Equity": ("Equity", "equity"),
    "CurrentAssets": ("CurrentAssets", "current_assets"),
    "creditors_within_one_year": (
        "creditors_within_one_year",
        "creditors_within_one_year",
    ),
    "NetCurrentAssetsLiabilities": ("NetCurrentAssetsLiabilities", "net_current_assets"),
    "CashBankOnHand": ("CashBankOnHand", "cash"),
    "AverageNumberEmployeesDuringPeriod": (
        "AverageNumberEmployeesDuringPeriod",
        "employees",
    ),
}

NUMERIC_SUMMARIES = (
    "n_periods_available",
    "months_since_latest_period_end",
    "prior_gap_months",
    "equity",
    "current_assets",
    "creditors_within_one_year",
    "net_current_assets",
    "cash",
    "current_ratio",
    "d_equity",
    "d_net_current_assets",
    "d_cash",
)


@dataclass(frozen=True)
class CaseCohort:
    frame: Any
    flow: dict[str, Any]


def _month_to_index(value: str) -> int:
    year, month = (int(part) for part in value.split("-"))
    return year * 12 + month - 1


def _index_to_yyyymm(value: int) -> int:
    year, month0 = divmod(value, 12)
    return year * 100 + month0 + 1


def cutoff_yyyymm(event_month: str, lead_months: int) -> int:
    return _index_to_yyyymm(_month_to_index(event_month) - lead_months)


def previous_yyyymm(value: int) -> int:
    return _index_to_yyyymm((value // 100) * 12 + value % 100 - 2)


def build_case_cohort(labels_path: str | Path) -> CaseCohort:
    """Load the fixed label cohort using the existing loader's disposition rules."""
    pl = require_polars()
    labels: LabelSet = load_labels(labels_path)
    supported = {
        company: label
        for company, label in labels.labels.items()
        if label.case_type in SUPPORTED_CASE_TYPES
    }
    before = sum(label.month_registered < MIN_EVENT_MONTH for label in supported.values())
    after = sum(label.month_registered > MAX_EVENT_MONTH for label in supported.values())
    selected = {
        company: label
        for company, label in supported.items()
        if MIN_EVENT_MONTH <= label.month_registered <= MAX_EVENT_MONTH
    }
    rows = [
        {
            "company_number": company,
            "case_type": label.case_type,
            "event_month": label.month_registered,
            "event_year": int(label.month_registered[:4]),
        }
        for company, label in sorted(selected.items())
    ]
    frame = pl.DataFrame(
        rows,
        schema={
            "company_number": pl.String,
            "case_type": pl.String,
            "event_month": pl.String,
            "event_year": pl.Int32,
        },
    )
    if frame.height != frame["company_number"].n_unique():
        raise RuntimeError("case cohort company numbers are not unique")
    by_type = Counter(label.case_type for label in selected.values())
    row_exclusions = (
        labels.dropped_bulk
        + labels.dropped_administration_to_cvl
        + len(labels.unusable)
        + labels.unusable_shifted
    )
    rows_before_deduplication = labels.input_rows - row_exclusions
    flow = {
        "input_rows": labels.input_rows,
        "dropped_bulk": labels.dropped_bulk,
        "dropped_administration_to_cvl": labels.dropped_administration_to_cvl,
        "unusable_company_number": len(labels.unusable),
        "unusable_month": labels.unusable_shifted,
        "row_exclusions_before_deduplication": row_exclusions,
        "rows_after_exclusions_before_deduplication": rows_before_deduplication,
        "additional_company_rows_removed_by_deduplication": labels.duplicate_rows,
        "retained_unique_companies": len(labels.labels),
        "unique_event_count": None,
        "unique_event_count_reason": (
            "the source has no event identifier and the loader retains one label row per company"
        ),
        "unsupported_retained_event_type": len(labels.labels) - len(supported),
        "supported_unique_companies": len(supported),
        "event_before_2015_01": before,
        "event_after_2024_04": after,
        "candidate_companies": frame.height,
        "candidate_by_case_type": dict(sorted(by_type.items())),
    }
    accounted = (
        labels.dropped_bulk
        + labels.dropped_administration_to_cvl
        + len(labels.unusable)
        + labels.unusable_shifted
        + labels.duplicate_rows
        + len(labels.labels)
    )
    if accounted != labels.input_rows:
        raise RuntimeError(
            f"label flow does not reconcile: dispositions={accounted}, input={labels.input_rows}"
        )
    return CaseCohort(frame=frame, flow=flow)


def build_case_cutoffs(cohort: CaseCohort):
    """Expand each case to all predeclared leads and availability conventions."""
    pl = require_polars()
    rows = []
    for case in cohort.frame.iter_rows(named=True):
        for lead_months in LEAD_MONTHS:
            cutoff = cutoff_yyyymm(case["event_month"], lead_months)
            for convention in CONVENTIONS:
                availability = cutoff if convention == "registration_month" else previous_yyyymm(cutoff)
                rows.append(
                    {
                        **case,
                        "lead_months": lead_months,
                        "convention": convention,
                        "cutoff_yyyymm": cutoff,
                        "availability_cutoff_yyyymm": availability,
                    }
                )
    return pl.DataFrame(rows).with_columns(
        pl.col("lead_months").cast(pl.Int16),
        pl.col("cutoff_yyyymm").cast(pl.Int32),
        pl.col("availability_cutoff_yyyymm").cast(pl.Int32),
    )


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _input_record(path: str | Path) -> dict[str, Any]:
    resolved = Path(path)
    return {
        "path": str(resolved),
        "bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def _rows_as_dicts(cursor) -> list[dict[str, Any]]:
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _create_candidate_inputs(con, wide_path: str, provenance_path: str) -> None:
    planned = ", ".join(_sql_literal(column) for column in CELL_COLUMNS)
    con.execute(
        f"""
        CREATE TEMP TABLE candidate_provenance AS
        SELECT p.company, p.period_end, p.wide_column, p.source_year, p.source_month
        FROM read_parquet({_sql_literal(provenance_path)}) p
        SEMI JOIN (SELECT DISTINCT company_number FROM case_cutoffs) c
          ON p.company = c.company_number
        WHERE p.wide_column IN ({planned})
        """
    )
    duplicate_cells = con.sql(
        """
        SELECT count(*) - count(DISTINCT (company, period_end, wide_column))
        FROM candidate_provenance
        """
    ).fetchone()[0]
    if duplicate_cells:
        raise RuntimeError(f"candidate provenance has {duplicate_cells} duplicate cell keys")
    con.execute(
        f"""
        CREATE TEMP TABLE candidate_wide AS
        SELECT w.*
        FROM read_parquet({_sql_literal(wide_path)}) w
        SEMI JOIN (SELECT DISTINCT company_number FROM case_cutoffs) c
          ON w.company = c.company_number
        """
    )
    duplicate_periods = con.sql(
        "SELECT count(*) - count(DISTINCT (company, period_end)) FROM candidate_wide"
    ).fetchone()[0]
    if duplicate_periods:
        raise RuntimeError(f"candidate WIDE has {duplicate_periods} duplicate period keys")


def _create_features(con) -> None:
    cell_expressions = []
    for provenance_column, (wide_column, output_column) in CELL_COLUMNS.items():
        value = f'w."{wide_column}"'
        cell_expressions.append(
            f"max(CASE WHEN p.wide_column = {_sql_literal(provenance_column)} "
            f"THEN {value} END) AS {output_column}"
        )
    anomaly = (
        "max(CASE WHEN p.wide_column = 'AverageNumberEmployeesDuringPeriod' "
        "THEN w.employees_unit_anomaly END) AS employees_unit_anomaly"
    )
    con.execute(
        f"""
        CREATE TEMP TABLE eligible_periods AS
        SELECT c.company_number, c.case_type, c.event_month, c.event_year,
               c.lead_months, c.convention, c.cutoff_yyyymm,
               try_cast(p.period_end AS DATE) AS period_end,
               {", ".join(cell_expressions)},
               {anomaly}
        FROM case_cutoffs c
        JOIN candidate_provenance p
          ON p.company = c.company_number
         AND p.source_year * 100 + p.source_month <= c.availability_cutoff_yyyymm
        JOIN candidate_wide w
          ON w.company = p.company AND w.period_end = p.period_end
        WHERE try_cast(p.period_end AS DATE) >= DATE {_sql_literal(PLAUSIBLE_PERIOD_START)}
          AND try_cast(p.period_end AS DATE) <= make_date(c.cutoff_yyyymm // 100 + 1, 12, 31)
        GROUP BY c.company_number, c.case_type, c.event_month, c.event_year,
                 c.lead_months, c.convention, c.cutoff_yyyymm, p.period_end
        """
    )
    con.execute(
        """
        CREATE TEMP TABLE ranked_periods AS
        SELECT *,
               row_number() OVER (
                   PARTITION BY company_number, lead_months, convention
                   ORDER BY period_end DESC
               ) AS period_rank,
               count(*) OVER (
                   PARTITION BY company_number, lead_months, convention
               ) AS n_periods_available
        FROM eligible_periods
        """
    )
    con.execute(
        f"""
        CREATE TEMP TABLE features AS
        SELECT l.company_number, l.case_type, l.event_month, l.event_year,
               l.lead_months, l.convention, l.cutoff_yyyymm,
               l.period_end AS latest_period_end,
               p.period_end AS prior_period_end,
               l.n_periods_available,
               (l.cutoff_yyyymm // 100 - year(l.period_end)) * 12
                   + (l.cutoff_yyyymm % 100 - month(l.period_end))
                   AS months_since_latest_period_end,
               CASE WHEN p.period_end IS NULL THEN NULL
                    ELSE date_diff('month', p.period_end, l.period_end) END AS prior_gap_months,
               l.equity, l.current_assets, l.creditors_within_one_year,
               l.net_current_assets, l.cash,
               CASE WHEN l.equity IS NULL THEN NULL ELSE l.equity < 0 END AS negative_equity,
               CASE WHEN l.net_current_assets IS NULL THEN NULL
                    ELSE l.net_current_assets < 0 END AS net_current_liabilities,
               CASE WHEN l.creditors_within_one_year IS NULL
                          OR l.creditors_within_one_year = 0
                    THEN NULL ELSE l.current_assets / l.creditors_within_one_year END
                    AS current_ratio,
               CASE WHEN l.employees IS NULL THEN NULL
                    WHEN l.employees <= 0 THEN '0'
                    WHEN l.employees <= 10 THEN '1-10'
                    WHEN l.employees <= 50 THEN '11-50'
                    WHEN l.employees <= 250 THEN '51-250'
                    ELSE '251+' END AS employee_band,
               l.employees_unit_anomaly,
               CASE WHEN p.period_end IS NULL
                          OR date_diff('month', p.period_end, l.period_end) > {MAX_PRIOR_GAP_MONTHS}
                    THEN NULL ELSE l.equity - p.equity END AS d_equity,
               CASE WHEN p.period_end IS NULL
                          OR date_diff('month', p.period_end, l.period_end) > {MAX_PRIOR_GAP_MONTHS}
                    THEN NULL ELSE l.net_current_assets - p.net_current_assets END
                    AS d_net_current_assets,
               CASE WHEN p.period_end IS NULL
                          OR date_diff('month', p.period_end, l.period_end) > {MAX_PRIOR_GAP_MONTHS}
                    THEN NULL ELSE l.cash - p.cash END AS d_cash
        FROM ranked_periods l
        LEFT JOIN ranked_periods p
          ON p.company_number = l.company_number
         AND p.lead_months = l.lead_months
         AND p.convention = l.convention
         AND p.period_rank = 2
        WHERE l.period_rank = 1
        """
    )


def _aggregate(con) -> dict[str, Any]:
    observed_columns = (
        "equity",
        "current_assets",
        "creditors_within_one_year",
        "net_current_assets",
        "cash",
        "current_ratio",
        "employee_band",
        "employees_unit_anomaly",
        "d_equity",
        "d_net_current_assets",
        "d_cash",
    )
    observed_sql = ",\n".join(
        f"count(f.{column}) AS {column}_observed" for column in observed_columns
    )
    summary = _rows_as_dicts(
        con.execute(
            f"""
            SELECT c.lead_months, c.convention,
                   count(*) AS candidates,
                   count(f.company_number) AS any_accounts,
                   {observed_sql},
                   count(f.negative_equity) AS negative_equity_observed,
                   count(*) FILTER (WHERE f.negative_equity) AS negative_equity_true,
                   count(f.net_current_liabilities) AS net_current_liabilities_observed,
                   count(*) FILTER (WHERE f.net_current_liabilities)
                       AS net_current_liabilities_true,
                   count(*) FILTER (WHERE f.employees_unit_anomaly = 1)
                       AS employees_unit_anomaly_true
            FROM case_cutoffs c
            LEFT JOIN features f USING (company_number, lead_months, convention)
            GROUP BY c.lead_months, c.convention
            ORDER BY c.lead_months, c.convention
            """
        )
    )
    stats_sql = []
    for column in NUMERIC_SUMMARIES:
        stats_sql.extend(
            [
                f"count({column}) AS {column}__n",
                f"quantile_cont({column}, 0.25) AS {column}__q25",
                f"median({column}) AS {column}__median",
                f"quantile_cont({column}, 0.75) AS {column}__q75",
            ]
        )
    numeric_rows = _rows_as_dicts(
        con.execute(
            f"""
            SELECT lead_months, convention, {", ".join(stats_sql)}
            FROM features
            GROUP BY lead_months, convention
            ORDER BY lead_months, convention
            """
        )
    )
    numeric = []
    for row in numeric_rows:
        for column in NUMERIC_SUMMARIES:
            numeric.append(
                {
                    "lead_months": row["lead_months"],
                    "convention": row["convention"],
                    "attribute": column,
                    "observed": row[f"{column}__n"],
                    "q25": row[f"{column}__q25"],
                    "median": row[f"{column}__median"],
                    "q75": row[f"{column}__q75"],
                }
            )
    by_type = _rows_as_dicts(
        con.execute(
            """
            SELECT c.lead_months, c.convention, c.case_type,
                   count(*) AS candidates, count(f.company_number) AS any_accounts
            FROM case_cutoffs c
            LEFT JOIN features f USING (company_number, lead_months, convention)
            GROUP BY c.lead_months, c.convention, c.case_type
            ORDER BY c.lead_months, c.convention, c.case_type
            """
        )
    )
    by_year = _rows_as_dicts(
        con.execute(
            """
            SELECT c.lead_months, c.convention, c.event_year,
                   count(*) AS candidates, count(f.company_number) AS any_accounts
            FROM case_cutoffs c
            LEFT JOIN features f USING (company_number, lead_months, convention)
            GROUP BY c.lead_months, c.convention, c.event_year
            ORDER BY c.lead_months, c.convention, c.event_year
            """
        )
    )
    employee_bands = _rows_as_dicts(
        con.execute(
            """
            SELECT lead_months, convention, employee_band, count(*) AS observed
            FROM features
            WHERE employee_band IS NOT NULL
            GROUP BY lead_months, convention, employee_band
            ORDER BY lead_months, convention, employee_band
            """
        )
    )
    return {
        "cutoff_summary": summary,
        "numeric_summaries": numeric,
        "coverage_by_case_type": by_type,
        "coverage_by_event_year": by_year,
        "employee_bands": employee_bands,
    }


def run_lead_time_analysis(
    labels_path: str | Path,
    wide_path: str | Path,
    provenance_path: str | Path,
    *,
    memory_limit_gb: int = 8,
    spill_dir: str | Path = "/tmp/ukcompany-lead-time-spill",
) -> dict[str, Any]:
    """Run the aggregate-only study and return a JSON-serialisable report."""
    started = time.perf_counter()
    cohort = build_case_cohort(labels_path)
    cutoffs = build_case_cutoffs(cohort)
    expected_cutoffs = cohort.frame.height * len(LEAD_MONTHS) * len(CONVENTIONS)
    if cutoffs.height != expected_cutoffs:
        raise RuntimeError(f"cutoff expansion failed: {cutoffs.height} != {expected_cutoffs}")

    inputs = {
        "labels": _input_record(labels_path),
        "wide_as_first_reported": _input_record(wide_path),
        "cell_provenance_as_first_reported": _input_record(provenance_path),
    }
    con = _connect(memory_limit_gb, str(spill_dir))
    try:
        con.register("case_cutoffs_input", cutoffs.to_arrow())
        con.execute("CREATE TEMP TABLE case_cutoffs AS SELECT * FROM case_cutoffs_input")
        _create_candidate_inputs(con, str(wide_path), str(provenance_path))
        _create_features(con)
        aggregates = _aggregate(con)
    finally:
        con.close()
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_bytes = peak if __import__("sys").platform == "darwin" else peak * 1024
    return {
        "study": "accounts-only historical case lead-time",
        "aggregate_only": True,
        "code_commit": _git_commit(),
        "inputs": inputs,
        "specification": {
            "event_window": [MIN_EVENT_MONTH, MAX_EVENT_MONTH],
            "supported_case_types": list(SUPPORTED_CASE_TYPES),
            "lead_months": list(LEAD_MONTHS),
            "conventions": list(CONVENTIONS),
            "cell_availability": "source_year * 100 + source_month <= availability cutoff",
            "uses_row_available_yyyymm": False,
            "one_cycle_lag": "source registration month is usable from the next month",
            "planned_attributes": [
                "equity",
                "current_assets",
                "creditors_within_one_year",
                "net_current_assets",
                "cash",
                "negative_equity",
                "net_current_liabilities",
                "current_ratio",
                "employee_band",
                "employees_unit_anomaly",
                "d_equity",
                "d_net_current_assets",
                "d_cash",
            ],
        },
        "cohort_flow": cohort.flow,
        **aggregates,
        "runtime": {
            "seconds": time.perf_counter() - started,
            "peak_rss_bytes": peak_bytes,
            "memory_limit_gb": memory_limit_gb,
        },
    }


def write_aggregate_json(report: dict[str, Any], path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return output
