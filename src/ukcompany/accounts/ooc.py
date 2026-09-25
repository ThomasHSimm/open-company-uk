"""Out-of-core restatement and pivot for full-history scale (DuckDB).

The sample-scale implementations do not scale to full history: the Python-dict
restatement tally needed 17.8 GB over 24 months (dict overhead 5-10x the data), and the
sort-based pivot needed ~24 GB over 30 archives — both would exceed a ~30 GB machine over
~7x more data. DuckDB spills to disk automatically for group-bys, window functions, and
joins that don't fit in RAM, so both are re-expressed as SQL over `read_parquet(glob)`
rather than Python-level dict/DataFrame accumulation. Definitions are unchanged from the
validated sample-scale versions (qa.restatement_rate_over_parts, pivot.pivot_long); this
module only changes the execution engine.
"""

from __future__ import annotations

from pathlib import Path

from .core import EMPLOYEE_CONCEPT, NIL_RAW_VALUES, TARGET_CONCEPTS
from .pivot import WideColumnMap, require_polars
from .qa import RestatementRateResult, render_qa_report

DEFAULT_MEMORY_LIMIT_GB = 8
DEFAULT_SPILL_DIR = "data/accounts/.duckdb-spill"


def require_duckdb():
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError("out-of-core accounts outputs require the duckdb package") from exc
    return duckdb


def _connect(memory_limit_gb: int = DEFAULT_MEMORY_LIMIT_GB, spill_dir: str = DEFAULT_SPILL_DIR):
    """A dedicated, explicitly bounded connection — not the implicit default connection.

    DuckDB's default `memory_limit` is a large fraction of system RAM, so an unconfigured
    connection does not actually spill to disk until it has already consumed most of the
    machine's memory: measured to still OOM at a 20 GB cgroup cap for the pivot query
    despite DuckDB's out-of-core design, because nothing told it to stay under that cap or
    where to spill. Setting both explicitly is what makes this genuinely out-of-core.
    """
    duckdb = require_duckdb()
    Path(spill_dir).mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(":memory:")
    connection.execute(f"SET memory_limit = '{int(memory_limit_gb)}GB'")
    connection.execute(f"SET temp_directory = {_sql_literal(spill_dir)}")
    return connection


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


_NIL_RAW_VALUES_SQL = "(" + ", ".join(_sql_literal(v) for v in NIL_RAW_VALUES) + ")"


def restatement_rate_duckdb(
    parts: str | Path,
    *,
    scope_label: str,
    memory_limit_gb: int = DEFAULT_MEMORY_LIMIT_GB,
    spill_dir: str = DEFAULT_SPILL_DIR,
) -> RestatementRateResult:
    """Same definition as `qa.restatement_rate_over_parts` (panel check's 7.94%, validated
    at sample scale as 7.93%), computed via a DuckDB window function instead of a Python
    dict running tally. `dimension IS NULL`, `status = 'selected'`, numeric, the nine
    target concepts, keyed by (company, period_end, concept); "repeated" = key appears in
    >=2 filings; "disagree" = a later filing (by source_year, source_month) reports a
    different scale-normalised value than the first one seen. A bare dash
    (`NIL_RAW_VALUES`) is treated as a genuine value of 0, not excluded.
    """
    connection = _connect(memory_limit_gb, spill_dir)
    concepts_sql = ", ".join(_sql_literal(concept) for concept in TARGET_CONCEPTS)
    parts_sql = _sql_literal(str(parts))
    query = f"""
        WITH facts AS (
            SELECT company, period_end, concept, source_year, source_month,
                CASE WHEN numeric_value IS NULL THEN '0' ELSE numeric_value END AS numeric_value
            FROM read_parquet({parts_sql})
            WHERE concept IN ({concepts_sql})
              AND status = 'selected'
              AND dimension IS NULL
              AND (numeric_value IS NOT NULL OR raw_value IN {_NIL_RAW_VALUES_SQL})
        ),
        ordered AS (
            SELECT
                company, period_end, concept, numeric_value,
                FIRST_VALUE(numeric_value) OVER (
                    PARTITION BY company, period_end, concept
                    ORDER BY source_year, source_month
                    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
                ) AS first_value,
                COUNT(*) OVER (PARTITION BY company, period_end, concept) AS n
            FROM facts
        ),
        per_key AS (
            SELECT company, period_end, concept, ANY_VALUE(n) AS n,
                   MAX(CASE WHEN numeric_value != first_value THEN 1 ELSE 0 END) AS disagrees
            FROM ordered
            GROUP BY company, period_end, concept
        )
        SELECT
            concept,
            COUNT(*) FILTER (WHERE n >= 2) AS repeated,
            COALESCE(SUM(disagrees) FILTER (WHERE n >= 2), 0) AS disagree,
            COUNT(*) AS keys_total_for_concept
        FROM per_key
        GROUP BY concept
    """
    try:
        rows = connection.sql(query).fetchall()
    finally:
        connection.close()
    by_concept_map = {row[0]: (int(row[1]), int(row[2])) for row in rows}
    keys_total = sum(int(row[3]) for row in rows)
    by_concept = tuple(
        (concept, *by_concept_map.get(concept, (0, 0))) for concept in sorted(TARGET_CONCEPTS)
    )
    keys_repeated = sum(repeated for _concept, repeated, _disagree in by_concept)
    keys_disagree = sum(disagree for _concept, _repeated, disagree in by_concept)
    return RestatementRateResult(
        scope_label=scope_label,
        keys_total=keys_total,
        keys_repeated=keys_repeated,
        keys_disagree=keys_disagree,
        by_concept=by_concept,
    )


_NEVER_MATCHES = "'__never-matches-a-real-concept-name__'"


def _totals_values_sql(mapping: WideColumnMap) -> str:
    rows = [f"({_sql_literal(total)}, {_sql_literal(total)})" for total in mapping.totals]
    if not rows:
        rows = [f"({_NEVER_MATCHES}, {_NEVER_MATCHES})"]
    return "VALUES " + ", ".join(rows)


def _members_values_sql(mapping: WideColumnMap) -> str:
    rows = [
        f"({_sql_literal(member.concept)}, {_sql_literal(member.dimension)}, "
        f"{_sql_literal(member.member)}, {_sql_literal(member.column)})"
        for member in mapping.members
    ]
    if not rows:
        rows = [f"({_NEVER_MATCHES}, {_NEVER_MATCHES}, {_NEVER_MATCHES}, {_NEVER_MATCHES})"]
    return "VALUES " + ", ".join(rows)


def _cells_with_sql(parts: str | Path, mapping: WideColumnMap, mode: str) -> str:
    """The `WITH ... ranked AS (...)` prefix shared by both output queries below.

    A numeric fact filed as a bare dash (`NIL_RAW_VALUES`) means nil and is coalesced to `'0'`
    here rather than excluded — it competes in the ranking on equal footing with a real value
    from another filing, so a dash in the winning filing legitimately produces a `0` cell
    (see `test_dash_in_original_filing_wins_as_first_reported_as_zero`), rather than being
    skipped in favour of some other filing's number.

    Totals and members are joined separately (then UNION ALL'd), mirroring
    `pivot._mapped_cells`, rather than one join with an OR condition: an OR across two
    different equality shapes defeats DuckDB's hash-join planning and was measured to
    force a much more expensive plan that OOM'd at full-corpus scale. Empty totals/members
    lists are handled by a never-matching sentinel row in the VALUES clause (see
    `_totals_values_sql`/`_members_values_sql`), so both branches are always safe to join
    unconditionally, keeping the UNION ALL's column count consistent.
    """
    direction = "ASC" if mode == "as_first_reported" else "DESC"
    extra_filter = "AND is_current = 1" if mode == "as_first_reported" else ""
    usable_filter = (
        f"f.status = 'selected' AND (f.currency = 'GBP' "
        f"OR f.concept = {_sql_literal(EMPLOYEE_CONCEPT)}) "
        f"AND (f.numeric_value IS NOT NULL OR f.raw_value IN {_NIL_RAW_VALUES_SQL}) "
        f"{extra_filter}"
    )
    parts_sql = _sql_literal(str(parts))
    totals_values_sql = _totals_values_sql(mapping)
    members_values_sql = _members_values_sql(mapping)
    select_cols = (
        "f.company, f.period_end, m.wide_column, f.source_year, f.source_month, "
        "f.source_archive, f.source_member, f.made_up_to_date, f.unit, "
        "CASE WHEN f.numeric_value IS NULL THEN '0' ELSE f.numeric_value END AS numeric_value"
    )
    totals_cte = (
        f"SELECT {select_cols} FROM read_parquet({parts_sql}) f "
        f"JOIN totals_map m ON f.concept = m.concept "
        f"WHERE f.dimension IS NULL AND {usable_filter}"
    )
    members_cte = (
        f"SELECT {select_cols} FROM read_parquet({parts_sql}) f "
        f"JOIN members_map m ON f.concept = m.concept "
        f"AND f.dimension = m.dimension AND f.member = m.member "
        f"WHERE {usable_filter}"
    )
    return f"""
        WITH totals_map(concept, wide_column) AS ({totals_values_sql}),
        members_map(concept, dimension, member, wide_column) AS ({members_values_sql}),
        cells AS (
            {totals_cte}
            UNION ALL
            {members_cte}
        ),
        ranked AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY company, period_end, wide_column
                    ORDER BY source_year {direction}, source_month {direction},
                             source_member {direction}
                ) AS rn
            FROM cells
        ),
        selected AS (
            SELECT company, period_end, wide_column, source_year, source_month,
                   source_archive, source_member, made_up_to_date, unit,
                   TRY_CAST(numeric_value AS DOUBLE) AS numeric_value
            FROM ranked
            WHERE rn = 1
        )
    """


def pivot_duckdb(
    parts: str | Path,
    mapping: WideColumnMap,
    mode: str,
    wide_output: str | Path,
    provenance_output: str | Path,
    *,
    memory_limit_gb: int = DEFAULT_MEMORY_LIMIT_GB,
    spill_dir: str = DEFAULT_SPILL_DIR,
) -> None:
    """Same definition as `pivot.pivot_long` (as_first_reported = earliest source per
    company-period-column; latest = latest source), computed via DuckDB window functions
    over `read_parquet(glob)` and written directly to Parquet — never materialised as an
    in-memory DataFrame. Provenance is cell-level (as large as the mapped-cell corpus,
    tens of millions of rows at full-history scale); bringing that into Python/Polars
    memory via `.pl()`, even with `memory_limit` bounding DuckDB's own operators, was
    measured to still OOM, because a query *result* materialising to Arrow happens after
    DuckDB's internal spill accounting. `COPY ... TO ... (FORMAT PARQUET)` streams DuckDB's
    own output writer instead, which is what makes this genuinely out-of-core.

    Every `AverageNumberEmployeesDuringPeriod` value is kept as-is, no matter its unit or
    size (see `docs/accounts-employee-unit-cutoff.md` for why an earlier value-cutoff was
    tried and then removed before publication). A companion `employees_unit_anomaly` column
    is still emitted: 1 if the winning employee fact for that row was GBP-tagged (a likely
    but unconfirmed unit mislabel), 0 for any other unit, `NULL` if no employee fact was
    selected for that row at all — diagnostic only, never used to alter a value.
    """
    mapping.validate()
    if mode not in {"latest", "as_first_reported"}:
        raise ValueError(f"unknown pivot mode: {mode}")
    cells_with_sql = _cells_with_sql(parts, mapping, mode)
    Path(wide_output).parent.mkdir(parents=True, exist_ok=True)
    Path(provenance_output).parent.mkdir(parents=True, exist_ok=True)

    column_exprs = [
        f'MAX(CASE WHEN wide_column = {_sql_literal(column)} THEN numeric_value END) '
        f'AS "{column}"'
        for column in mapping.columns
    ]
    if EMPLOYEE_CONCEPT in mapping.columns:
        column_exprs.append(
            f"MAX(CASE WHEN wide_column = {_sql_literal(EMPLOYEE_CONCEPT)} THEN "
            f"CASE WHEN unit = 'GBP' THEN 1 ELSE 0 END END) AS employees_unit_anomaly"
        )
    column_exprs = ", ".join(column_exprs)
    wide_sql = f"""
        {cells_with_sql}
        SELECT company, period_end,
            {column_exprs},
            COUNT(DISTINCT wide_column) AS n_concepts_present,
            COUNT(DISTINCT source_year || '-' || source_month || '-' ||
                  source_archive || '-' || source_member) AS n_source_filings,
            MAX(source_year * 100 + source_month) AS row_available_yyyymm
        FROM selected
        GROUP BY company, period_end
        ORDER BY company, period_end
    """
    provenance_sql = f"""
        {cells_with_sql}
        SELECT company, period_end, wide_column, source_year, source_month,
               source_member, made_up_to_date
        FROM selected
        ORDER BY company, period_end, wide_column
    """
    connection = _connect(memory_limit_gb, spill_dir)
    try:
        connection.execute(
            f"COPY ({wide_sql}) TO {_sql_literal(str(wide_output))} "
            f"(FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        connection.execute(
            f"COPY ({provenance_sql}) TO {_sql_literal(str(provenance_output))} "
            f"(FORMAT PARQUET, COMPRESSION ZSTD)"
        )
    finally:
        connection.close()


def member_histogram_duckdb(
    parts: str | Path,
    *,
    memory_limit_gb: int = DEFAULT_MEMORY_LIMIT_GB,
    spill_dir: str = DEFAULT_SPILL_DIR,
):
    """Same definition as `qa.member_histogram`, computed via a single DuckDB group-by.

    `companies`/`company_periods` are genuine `COUNT(DISTINCT ...)`, safe here (unlike the
    per-file Polars version's separate distinct-tuple pass) because DuckDB's grouped
    aggregates spill to disk under `memory_limit` rather than needing every distinct value
    resident at once.
    """
    concepts_sql = ", ".join(_sql_literal(concept) for concept in TARGET_CONCEPTS)
    parts_sql = _sql_literal(str(parts))
    query = f"""
        SELECT concept, dimension, member,
            COUNT(*) AS observations,
            COUNT(DISTINCT company) AS companies,
            COUNT(DISTINCT company || '\x1f' || CAST(period_end AS VARCHAR)) AS company_periods
        FROM read_parquet({parts_sql})
        WHERE concept IN ({concepts_sql})
          AND status = 'selected'
          AND dimension IS NOT NULL
        GROUP BY concept, dimension, member
        ORDER BY concept, observations DESC
    """
    connection = _connect(memory_limit_gb, spill_dir)
    try:
        return connection.sql(query).pl()
    finally:
        connection.close()


def total_component_reconciliation_duckdb(
    parts: str | Path,
    relative_tolerance: float = 1e-6,
    *,
    memory_limit_gb: int = DEFAULT_MEMORY_LIMIT_GB,
    spill_dir: str = DEFAULT_SPILL_DIR,
):
    """Same definition as `qa.total_component_reconciliation`, computed via DuckDB.

    `SOURCE_KEYS` (see qa.py) includes `source_archive`, so the totals-to-components join is
    file-local by construction — the same insight `total_component_reconciliation_over_parts`
    uses to bound Polars memory per-file. The row-level `comparisons` table is never brought
    back to Python (it is as large as the mapped-cell corpus, tens of millions of rows at
    full-history scale, and `write_qa` never reads it — only the small per-concept summary):
    the summary aggregation runs inside the same SQL statement, so only ~9 rows cross the
    DuckDB/Python boundary.
    """
    concepts_sql = ", ".join(_sql_literal(concept) for concept in TARGET_CONCEPTS)
    parts_sql = _sql_literal(str(parts))
    key_cols = "company, period_end, concept, source_year, source_month, source_archive, source_member"
    query = f"""
        WITH facts AS (
            SELECT {key_cols}, dimension, TRY_CAST(numeric_value AS DOUBLE) AS value
            FROM read_parquet({parts_sql})
            WHERE concept IN ({concepts_sql})
              AND status = 'selected'
              AND numeric_value IS NOT NULL
              AND (currency = 'GBP' OR concept = {_sql_literal(EMPLOYEE_CONCEPT)})
        ),
        totals AS (
            SELECT {key_cols}, ANY_VALUE(value) AS total
            FROM facts
            WHERE dimension IS NULL
            GROUP BY {key_cols}
        ),
        components AS (
            SELECT {key_cols}, dimension, SUM(value) AS component_sum, COUNT(*) AS n_members
            FROM facts
            WHERE dimension IS NOT NULL
            GROUP BY {key_cols}, dimension
        ),
        comparisons AS (
            SELECT t.concept, t.total, c.component_sum,
                   ABS(t.total - c.component_sum) AS absolute_difference
            FROM totals t
            JOIN components c
              ON t.company = c.company AND t.period_end = c.period_end
             AND t.concept = c.concept AND t.source_year = c.source_year
             AND t.source_month = c.source_month AND t.source_archive = c.source_archive
             AND t.source_member = c.source_member
        ),
        flagged AS (
            SELECT concept, absolute_difference,
                (absolute_difference <= GREATEST(1.0, ABS(total) * {relative_tolerance}))
                    AS agrees
            FROM comparisons
        )
        SELECT concept,
            COUNT(*) AS comparisons,
            SUM(CASE WHEN agrees THEN 1 ELSE 0 END) AS agreements,
            MEDIAN(absolute_difference) AS median_absolute_difference
        FROM flagged
        GROUP BY concept
        ORDER BY concept
    """
    connection = _connect(memory_limit_gb, spill_dir)
    try:
        summary = connection.sql(query).pl()
    finally:
        connection.close()
    pl = require_polars()
    return summary.with_columns(
        (pl.col("agreements").cast(pl.Float64) / pl.col("comparisons").cast(pl.Float64)).alias(
            "agreement_rate"
        )
    )


def write_qa_duckdb(
    long_path: str | Path,
    histogram_output: str | Path,
    reconciliation_output: str | Path,
    report_output: str | Path,
    *,
    memory_limit_gb: int = DEFAULT_MEMORY_LIMIT_GB,
    spill_dir: str = DEFAULT_SPILL_DIR,
) -> None:
    """Out-of-core equivalent of `qa.write_qa`, for corpora too large for the per-file
    Polars pass (measured to OOM at a 25 GB cgroup cap at full 152-archive scale)."""
    histogram = member_histogram_duckdb(long_path, memory_limit_gb=memory_limit_gb, spill_dir=spill_dir)
    reconciliation = total_component_reconciliation_duckdb(
        long_path, memory_limit_gb=memory_limit_gb, spill_dir=spill_dir
    )
    for output in (histogram_output, reconciliation_output, report_output):
        Path(output).parent.mkdir(parents=True, exist_ok=True)
    histogram.write_csv(histogram_output)
    reconciliation.write_csv(reconciliation_output)
    Path(report_output).write_text(
        render_qa_report(histogram, reconciliation, source=str(long_path)),
        encoding="utf-8",
    )


CREDITORS_MATURITY_DIMENSION = "MaturitiesOrExpirationPeriodsDimension"


def creditors_maturity_reconciliation_duckdb(
    parts: str | Path,
    *,
    relative_tolerance: float = 1e-6,
    examples_per_bucket: int = 5,
    memory_limit_gb: int = DEFAULT_MEMORY_LIMIT_GB,
    spill_dir: str = DEFAULT_SPILL_DIR,
):
    """Bucket every (Creditors total, MaturitiesOrExpirationPeriodsDimension components)
    pair that exists in the same filing, to decide whether the maturity split is safe to
    publish as its own WIDE columns.

    Buckets, in priority order (a key can only land in one):
    - `incomplete_axis`: exactly one of `WithinOneYear`/`AfterOneYear` present — this filing
      only reported half the split, so a mismatch here says nothing about the axis itself.
    - `match`: within the same tolerance as `qa.total_component_reconciliation`
      (max(£1, 1e-6 × |total|)).
    - `sign_flip`: the component sum is within tolerance of *negative* the total — the
      values are individually usable but the sign convention is inverted somewhere.
    - `other`: neither.

    Returns `(summary, examples)`: `summary` is one row per bucket (count, share); `examples`
    is up to `examples_per_bucket` sampled rows per bucket for manual inspection.
    """
    parts_sql = _sql_literal(str(parts))
    key_cols = "company, period_end, source_year, source_month, source_archive, source_member"
    query = f"""
        WITH facts AS (
            SELECT {key_cols}, dimension, member, TRY_CAST(numeric_value AS DOUBLE) AS value
            FROM read_parquet({parts_sql})
            WHERE concept = 'Creditors'
              AND status = 'selected'
              AND numeric_value IS NOT NULL
              AND currency = 'GBP'
        ),
        totals AS (
            SELECT {key_cols}, ANY_VALUE(value) AS total
            FROM facts
            WHERE dimension IS NULL
            GROUP BY {key_cols}
        ),
        maturity AS (
            SELECT {key_cols},
                SUM(value) AS component_sum,
                COUNT(*) AS n_members,
                MAX(CASE WHEN member = 'WithinOneYear' THEN 1 ELSE 0 END) AS has_within,
                MAX(CASE WHEN member = 'AfterOneYear' THEN 1 ELSE 0 END) AS has_after
            FROM facts
            WHERE dimension = {_sql_literal(CREDITORS_MATURITY_DIMENSION)}
            GROUP BY {key_cols}
        ),
        joined AS (
            SELECT t.company, t.period_end, t.source_year, t.source_month, t.source_archive,
                   t.source_member, t.total, m.component_sum, m.n_members, m.has_within,
                   m.has_after,
                   ABS(t.total - m.component_sum) AS abs_diff,
                   ABS(t.total + m.component_sum) AS abs_diff_flipped,
                   GREATEST(1.0, ABS(t.total) * {relative_tolerance}) AS tolerance
            FROM totals t
            JOIN maturity m
              ON t.company = m.company AND t.period_end = m.period_end
             AND t.source_year = m.source_year AND t.source_month = m.source_month
             AND t.source_archive = m.source_archive AND t.source_member = m.source_member
        ),
        bucketed AS (
            SELECT *,
                CASE
                    WHEN (has_within + has_after) = 1 THEN 'incomplete_axis'
                    WHEN abs_diff <= tolerance THEN 'match'
                    WHEN abs_diff_flipped <= tolerance THEN 'sign_flip'
                    ELSE 'other'
                END AS bucket
            FROM joined
        )
        SELECT * FROM bucketed
    """
    connection = _connect(memory_limit_gb, spill_dir)
    try:
        summary = connection.sql(
            f"SELECT bucket, COUNT(*) AS n FROM ({query}) GROUP BY bucket ORDER BY n DESC"
        ).pl()
        examples = connection.sql(
            f"""
            SELECT * FROM (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY bucket ORDER BY random()) AS rn
                FROM ({query})
            ) WHERE rn <= {int(examples_per_bucket)}
            ORDER BY bucket, rn
            """
        ).pl()
    finally:
        connection.close()
    pl = require_polars()
    total_n = summary["n"].sum()
    summary = summary.with_columns((pl.col("n") / total_n).alias("share"))
    return summary, examples.drop("rn")


def employee_unit_distribution_duckdb(
    parts: str | Path,
    *,
    cutoff_percentile: float = 0.999,
    memory_limit_gb: int = DEFAULT_MEMORY_LIMIT_GB,
    spill_dir: str = DEFAULT_SPILL_DIR,
):
    """Compare `AverageNumberEmployeesDuringPeriod` values by tagged unit, and derive a
    candidate cut-off: the point where GBP-tagged values pass `cutoff_percentile` of the
    `pure`-tagged distribution (default the 99.9th percentile — most `pure` values are
    genuine headcounts, so this treats the top 0.1% of that distribution as the boundary of
    plausibility for a value carrying the wrong unit label).

    Returns `(distribution, cutoff)`: `distribution` has one row per unit
    (count/median/p99/p99.9/p99.99/max); `cutoff` is the derived value and the resulting
    kept/nulled split of the GBP-tagged population. Kept as a standalone diagnostic — see
    `docs/accounts-employee-unit-cutoff.md` for the analysis this produced and why the
    resulting cut-off was tried in `pivot_duckdb` and then removed before publication
    (every employee value is now kept as-is; `employees_unit_anomaly` is diagnostic only).
    """
    parts_sql = _sql_literal(str(parts))
    query = f"""
        SELECT unit, TRY_CAST(numeric_value AS DOUBLE) AS value
        FROM read_parquet({parts_sql})
        WHERE concept = {_sql_literal(EMPLOYEE_CONCEPT)}
          AND status = 'selected'
          AND dimension IS NULL
          AND numeric_value IS NOT NULL
          AND unit IN ('GBP', 'pure')
    """
    connection = _connect(memory_limit_gb, spill_dir)
    try:
        distribution = connection.sql(
            f"""
            SELECT unit,
                COUNT(*) AS n,
                MEDIAN(value) AS median,
                QUANTILE_CONT(value, 0.99) AS p99,
                QUANTILE_CONT(value, 0.999) AS p999,
                QUANTILE_CONT(value, 0.9999) AS p9999,
                MAX(value) AS max_value
            FROM ({query})
            GROUP BY unit
            """
        ).pl()
        cutoff_row = connection.sql(
            f"SELECT QUANTILE_CONT(value, {cutoff_percentile}) AS cutoff "
            f"FROM ({query}) WHERE unit = 'pure'"
        ).fetchone()
        cutoff = float(cutoff_row[0])
        kept, nulled = connection.sql(
            f"""
            SELECT
                SUM(CASE WHEN value <= {cutoff} THEN 1 ELSE 0 END) AS kept,
                SUM(CASE WHEN value > {cutoff} THEN 1 ELSE 0 END) AS nulled
            FROM ({query}) WHERE unit = 'GBP'
            """
        ).fetchone()
    finally:
        connection.close()
    return distribution, {"cutoff": cutoff, "gbp_kept": int(kept), "gbp_nulled": int(nulled)}


def restatement_rate_by_year_duckdb(
    parts: str | Path,
    *,
    memory_limit_gb: int = DEFAULT_MEMORY_LIMIT_GB,
    spill_dir: str = DEFAULT_SPILL_DIR,
):
    """Same definition as `restatement_rate_duckdb`, grouped by the year each key was
    *first* reported rather than by concept — for the dataset card to say whether early
    years restate more or less than recent ones, honestly (report only, nothing corrected).
    A bare dash (`NIL_RAW_VALUES`) is treated as a genuine value of 0, not excluded.
    """
    concepts_sql = ", ".join(_sql_literal(concept) for concept in TARGET_CONCEPTS)
    parts_sql = _sql_literal(str(parts))
    query = f"""
        WITH facts AS (
            SELECT company, period_end, concept, source_year, source_month,
                CASE WHEN numeric_value IS NULL THEN '0' ELSE numeric_value END AS numeric_value
            FROM read_parquet({parts_sql})
            WHERE concept IN ({concepts_sql})
              AND status = 'selected'
              AND dimension IS NULL
              AND (numeric_value IS NOT NULL OR raw_value IN {_NIL_RAW_VALUES_SQL})
        ),
        ordered AS (
            SELECT
                company, period_end, concept, numeric_value,
                FIRST_VALUE(numeric_value) OVER w AS first_value,
                FIRST_VALUE(source_year) OVER w AS first_source_year,
                COUNT(*) OVER (PARTITION BY company, period_end, concept) AS n
            FROM facts
            WINDOW w AS (
                PARTITION BY company, period_end, concept
                ORDER BY source_year, source_month
                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
            )
        ),
        per_key AS (
            SELECT company, period_end, concept, ANY_VALUE(first_source_year) AS first_source_year,
                   ANY_VALUE(n) AS n,
                   MAX(CASE WHEN numeric_value != first_value THEN 1 ELSE 0 END) AS disagrees
            FROM ordered
            GROUP BY company, period_end, concept
        )
        SELECT
            first_source_year AS year,
            COUNT(*) AS keys_total,
            COUNT(*) FILTER (WHERE n >= 2) AS repeated,
            COALESCE(SUM(disagrees) FILTER (WHERE n >= 2), 0) AS disagree
        FROM per_key
        GROUP BY first_source_year
        ORDER BY first_source_year
    """
    connection = _connect(memory_limit_gb, spill_dir)
    try:
        result = connection.sql(query).pl()
    finally:
        connection.close()
    pl = require_polars()
    return result.with_columns(
        pl.when(pl.col("repeated") > 0)
        .then(pl.col("disagree").cast(pl.Float64) / pl.col("repeated").cast(pl.Float64))
        .otherwise(0.0)
        .alias("disagreement_rate")
    )
