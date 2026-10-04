"""Per-company PSC feature table from the bulk snapshot (Handoff 07, Task 2).

One row per company that appears in the snapshot, carrying the SAME features
``ukcompany.derive.derive_psc`` produces from the per-company API, under the SAME
definitions. The nature-of-control decomposition, kind classification and UK-company-number
format test are reused verbatim from ``ukcompany.psc_natures`` - there is deliberately no
second implementation of those rules here. The only work done in this module is per-company
aggregation (counts, maxima, distinct sets), which is exactly what derive_psc does in Python.

Design for scale (~16M records, ~11M companies): the heavy grouping runs in DuckDB, but the
psc_natures *functions* are applied in Python over the small DISTINCT vocabularies - the
~dozens of nature code-sets, the ~10 kinds, the distinct corporate registration numbers -
and joined back by key, so Python never iterates 11M rows and the result is byte-identical to
calling the function per company.

Two output tiers, chosen by ``data_governance`` (default True == governed):
  * **private**  - every feature, including the companies-per-person band (person-linkage).
  * **governed** - no person-derived linkage: the companies-per-person band is absent, and
    the written schema is asserted to not even contain the column.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ukcompany.psc_natures import (
    classify_kind,
    is_uk_company_number_format,
    summarise_natures,
)

from .loader import (
    DEFAULT_MEMORY_LIMIT_GB,
    DEFAULT_SPILL_DIR,
    PSC_PERSON_CATEGORIES,
    _connect,
    _sql_literal,
)

# The companies-per-person count bands (decision D2). A per-person count is bucketed into
# one of these; the per-company feature is the MAX band over the company's in-scope PSCs.
# Ordinal rank is used only to take that maximum.
PERSON_COUNT_BANDS = ("1", "2-10", "11+")
_BAND_RANK = {band: rank for rank, band in enumerate(PERSON_COUNT_BANDS)}

# Columns that carry person-derived linkage and must never appear in a governed feature
# table. Kept as one list so the written-schema assertion checks against the same names. The
# private tier emits BOTH scopes (ever = active + ceased, as Task C; active = current
# footprint); the governed tier emits neither.
GOVERNED_FEATURE_DROPPED = (
    "companies_per_person_band_ever",
    "companies_per_person_band_active",
)

# The feature columns that are person/ownership signals, in output order. Pipeline-only
# state (psc_fetch_status) is intentionally omitted: every company in the snapshot was, by
# definition, fetched - the bulk analogue carries no "not_fetched" case.
FEATURE_COLUMNS = (
    "company_number",
    "psc_n_records",
    "psc_n_ceased",
    "psc_natures_of_control",
    "psc_max_ownership_band",
    "psc_max_voting_band",
    "psc_has_appointment_rights",
    "psc_has_significant_influence",
    "psc_n_distinct_natures",
    "psc_n_individual",
    "psc_n_corporate",
    "psc_n_legal_person",
    "psc_n_super_secure",
    "psc_corporate_reg_numbers",
    "psc_n_corporate_uk_format_regno",
    "psc_unmapped_natures",
    "n_psc_id_verified",
    "n_psc_id_verification_due",
    "n_psc_id_statement_filed",
    "active_psc_statement_codes",
    "psc_information_state",
)


def _person_category_sql_list() -> str:
    return ", ".join(_sql_literal(c) for c in sorted(PSC_PERSON_CATEGORIES))


def _band_for_count(n: int) -> str:
    if n <= 1:
        return "1"
    if n <= 10:
        return "2-10"
    return "11+"


def build_psc_features(
    records_path: str | Path,
    noc_path: str | Path,
    output_dir: str | Path,
    snapshot_date: str,
    *,
    data_governance: bool = True,
    memory_limit_gb: int = DEFAULT_MEMORY_LIMIT_GB,
    spill_dir: str = DEFAULT_SPILL_DIR,
) -> dict:
    """Build the per-company PSC feature table and write it as Parquet.

    Returns a small report dict (row count, fill rates, tier, outputs)."""
    records_path = str(records_path)
    noc_path = str(noc_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    mode = "governed" if data_governance else "private"
    features_path = output_dir / "psc_company_features.parquet"
    report_path = output_dir / "features_report.json"

    con = _connect(memory_limit_gb, spill_dir)
    try:
        rec = f"read_parquet({_sql_literal(records_path)})"
        noc = f"read_parquet({_sql_literal(noc_path)})"
        person_cats = _person_category_sql_list()

        # Features are built from the GOVERNED load: it carries the pseudonymous person_key
        # (the only mode that computes it) plus every non-PII feature input, so both output
        # tiers derive from one source. A private load has raw PII but no person_key.
        source_columns = {row[0] for row in con.sql(
            f"DESCRIBE SELECT * FROM {rec}"
        ).fetchall()}
        if "person_key" not in source_columns:
            raise ValueError(
                "build_psc_features expects the governed load (person_key present); the "
                "given psc_records.parquet has no person_key column - load with "
                "--data-governance first"
            )

        # One pass to tag every record with the flags the aggregations need. is_person is
        # the CH "persons_of_significant_control_count" scope (same set the loader
        # reconciles); is_active == no ceased date (the bulk snapshot has no top-level
        # active/ceased counts, so this is precedence (c) of derive._psc_active_ceased).
        con.execute(
            f"""
            CREATE TEMP TABLE r AS
            SELECT
                company_number,
                record_id,
                kind,
                category,
                reg_number_raw,
                statement,
                person_key,
                -- derive_psc's active/ceased rule exactly: ceased := the per-item `ceased`
                -- boolean when present, else `ceased_on` presence; active := NOT ceased.
                (NOT COALESCE("ceased", ceased_on IS NOT NULL)) AS is_active,
                (category IN ({person_cats})) AS is_person,
                -- identity_verification_details block presence proxy: any extracted iv_*
                -- field present (iv_preferred_name is dropped in governed mode, so it is not
                -- part of this test). Mirrors derive._id_verification_counts' "block present".
                (iv_identity_verified_on_raw IS NOT NULL
                 OR iv_verification_start_on_raw IS NOT NULL
                 OR iv_verification_end_on_raw IS NOT NULL
                 OR iv_verification_statement_date_raw IS NOT NULL
                 OR iv_verification_statement_due_on_raw IS NOT NULL
                 OR iv_acsp_name IS NOT NULL
                 OR iv_aml_supervisory_bodies IS NOT NULL) AS iv_block_present,
                iv_identity_verified_on_raw,
                iv_verification_statement_due_on_raw,
                iv_verification_statement_date_raw
            FROM {rec}
            WHERE category <> 'totals' AND company_number IS NOT NULL
            """
        )

        # --- kind -> coarse category, via the shared classify_kind (one definition) ---
        distinct_kinds = [row[0] for row in con.sql(
            "SELECT DISTINCT kind FROM r WHERE kind IS NOT NULL"
        ).fetchall()]
        kind_map = pd.DataFrame(
            {"kind": distinct_kinds, "cat4": [classify_kind(k) for k in distinct_kinds]}
        )
        con.register("kind_map", kind_map)

        # --- per-company person-record aggregates (counts + IV, derive_psc scope) ---
        con.execute(
            """
            CREATE TEMP TABLE agg_person AS
            SELECT
                r.company_number,
                COUNT(*) AS psc_n_records,
                COUNT(*) FILTER (WHERE NOT r.is_active) AS psc_n_ceased,
                COUNT(*) FILTER (WHERE r.is_active AND km.cat4 = 'individual')
                    AS psc_n_individual,
                COUNT(*) FILTER (WHERE r.is_active AND km.cat4 = 'corporate')
                    AS psc_n_corporate,
                COUNT(*) FILTER (WHERE r.is_active AND km.cat4 = 'legal-person')
                    AS psc_n_legal_person,
                COUNT(*) FILTER (WHERE r.is_active AND km.cat4 = 'super-secure')
                    AS psc_n_super_secure,
                -- IV counts over ALL person records (active + ceased), per derive_psc.
                COUNT(*) FILTER (WHERE r.iv_block_present) AS n_psc_id_verified,
                COUNT(*) FILTER (
                    WHERE r.iv_block_present
                      AND r.iv_verification_statement_due_on_raw IS NOT NULL
                      AND r.iv_identity_verified_on_raw IS NULL
                ) AS n_psc_id_verification_due,
                COUNT(*) FILTER (
                    WHERE r.iv_block_present
                      AND r.iv_verification_statement_date_raw IS NOT NULL
                ) AS n_psc_id_statement_filed
            FROM r
            LEFT JOIN kind_map km USING (kind)
            WHERE r.is_person
            GROUP BY r.company_number
            """
        )

        # --- corporate registration numbers (active corporate records) ---
        con.execute(
            """
            CREATE TEMP TABLE agg_regno AS
            SELECT company_number,
                   list(reg_number_raw ORDER BY reg_number_raw) AS regnos
            FROM r
            LEFT JOIN kind_map km USING (kind)
            WHERE r.is_active AND km.cat4 = 'corporate' AND reg_number_raw IS NOT NULL
            GROUP BY company_number
            """
        )
        distinct_regnos = [row[0] for row in con.sql(
            "SELECT DISTINCT reg_number_raw FROM r "
            "LEFT JOIN kind_map km USING (kind) "
            "WHERE r.is_active AND km.cat4 = 'corporate' AND reg_number_raw IS NOT NULL"
        ).fetchall()]
        regno_uk = pd.DataFrame({
            "regno": distinct_regnos,
            "is_uk": [is_uk_company_number_format(x) for x in distinct_regnos],
        })
        con.register("regno_uk", regno_uk)

        # --- natures of control (active person records), via psc_noc + is_uk record join ---
        con.execute(
            f"""
            CREATE TEMP TABLE agg_natures AS
            SELECT r.company_number,
                   list_sort(list_distinct(list(n.right_raw))) AS natures
            FROM {noc} n
            JOIN r ON n.record_id = r.record_id
            WHERE r.is_active AND r.is_person
            GROUP BY r.company_number
            """
        )

        # --- active statement codes (category='statement', not ceased) ---
        con.execute(
            """
            CREATE TEMP TABLE agg_statements AS
            SELECT company_number,
                   list_sort(list_distinct(list(statement))) AS statement_codes
            FROM r
            WHERE category = 'statement' AND is_active AND statement IS NOT NULL
            GROUP BY company_number
            """
        )

        # --- companies-per-person bands (private tier only), BOTH scopes ---
        # person_key is the HMAC of the baseline identity (forename+surname+DOB y/m), only
        # computable for individuals; restrict explicitly to individual kinds. Two scopes are
        # emitted: 'ever' (active + ceased, as Task C) and 'active' (current control
        # footprint). Each scope counts companies-per-person and takes the MAX band across the
        # company's individual records on the matching scope.
        individual_kinds = (
            "('individual-person-with-significant-control',"
            "'individual-beneficial-owner')"
        )
        for scope, active_clause in (("ever", ""), ("active", "AND r.is_active")):
            con.execute(
                f"""
                CREATE TEMP TABLE person_counts_{scope} AS
                SELECT person_key, COUNT(DISTINCT company_number) AS n_companies
                FROM r
                WHERE r.is_person AND r.person_key IS NOT NULL
                  AND r.kind IN {individual_kinds}
                  {active_clause}
                GROUP BY person_key
                """
            )
            pcc = con.sql(
                f"SELECT person_key, n_companies FROM person_counts_{scope}"
            ).fetchall()
            con.register(f"person_band_{scope}", pd.DataFrame({
                "person_key": [p for p, _ in pcc],
                "person_band_rank": [_BAND_RANK[_band_for_count(n)] for _, n in pcc],
            }))
            con.execute(
                f"""
                CREATE TEMP TABLE agg_cpp_{scope} AS
                SELECT r.company_number, MAX(pb.person_band_rank) AS band_rank
                FROM r
                JOIN person_band_{scope} pb USING (person_key)
                WHERE r.is_person {active_clause}
                  AND r.kind IN {individual_kinds}
                GROUP BY r.company_number
                """
            )

        # --- summarise_natures over DISTINCT code-sets (one call per set, joined back) ---
        SEP = "\x1f"
        distinct_sets = con.sql(
            f"SELECT DISTINCT array_to_string(natures, '{SEP}') AS key, natures "
            "FROM agg_natures"
        ).fetchall()
        summary_records = []
        for key, natures in distinct_sets:
            s = summarise_natures(natures)
            summary_records.append({
                "key": key,
                "psc_natures_of_control": ",".join(natures) if natures else None,
                "psc_max_ownership_band": s.max_ownership_band,
                "psc_max_voting_band": s.max_voting_band,
                "psc_has_appointment_rights": s.has_appointment_rights,
                "psc_has_significant_influence": s.has_significant_influence,
                "psc_n_distinct_natures": s.n_distinct_natures,
                "psc_unmapped_natures": ",".join(s.unmapped) if s.unmapped else None,
            })
        nature_summary = pd.DataFrame(summary_records)
        con.register("nature_summary", nature_summary)

        # --- company universe + assemble every feature by LEFT JOIN ---
        con.execute(
            f"""
            CREATE TEMP TABLE features AS
            WITH universe AS (
                SELECT DISTINCT company_number FROM r
            ),
            nat AS (
                SELECT an.company_number, ns.*
                FROM agg_natures an
                JOIN nature_summary ns
                  ON array_to_string(an.natures, '{SEP}') = ns.key
            )
            SELECT
                u.company_number,
                COALESCE(ap.psc_n_records, 0) AS psc_n_records,
                COALESCE(ap.psc_n_ceased, 0) AS psc_n_ceased,
                nat.psc_natures_of_control,
                nat.psc_max_ownership_band,
                nat.psc_max_voting_band,
                COALESCE(nat.psc_has_appointment_rights, FALSE) AS psc_has_appointment_rights,
                COALESCE(nat.psc_has_significant_influence, FALSE)
                    AS psc_has_significant_influence,
                COALESCE(nat.psc_n_distinct_natures, 0) AS psc_n_distinct_natures,
                COALESCE(ap.psc_n_individual, 0) AS psc_n_individual,
                COALESCE(ap.psc_n_corporate, 0) AS psc_n_corporate,
                COALESCE(ap.psc_n_legal_person, 0) AS psc_n_legal_person,
                COALESCE(ap.psc_n_super_secure, 0) AS psc_n_super_secure,
                array_to_string(ar.regnos, ',') AS psc_corporate_reg_numbers,
                COALESCE(uk.n_uk, 0) AS psc_n_corporate_uk_format_regno,
                nat.psc_unmapped_natures,
                COALESCE(ap.n_psc_id_verified, 0) AS n_psc_id_verified,
                COALESCE(ap.n_psc_id_verification_due, 0) AS n_psc_id_verification_due,
                COALESCE(ap.n_psc_id_statement_filed, 0) AS n_psc_id_statement_filed,
                array_to_string(st.statement_codes, ',') AS active_psc_statement_codes,
                CASE
                    WHEN COALESCE(ap.psc_n_records, 0) - COALESCE(ap.psc_n_ceased, 0) > 0
                        THEN 'identified'
                    WHEN st.statement_codes IS NOT NULL THEN 'statement_only'
                    ELSE 'none_reported'
                END AS psc_information_state,
                cpp_ever.band_rank AS _cpp_band_rank_ever,
                cpp_active.band_rank AS _cpp_band_rank_active
            FROM universe u
            LEFT JOIN agg_person ap USING (company_number)
            LEFT JOIN nat USING (company_number)
            LEFT JOIN agg_regno ar USING (company_number)
            LEFT JOIN (
                SELECT r.company_number, COUNT(*) AS n_uk
                FROM r
                LEFT JOIN kind_map km USING (kind)
                JOIN regno_uk ru ON r.reg_number_raw = ru.regno
                WHERE r.is_active AND km.cat4 = 'corporate' AND ru.is_uk
                GROUP BY r.company_number
            ) uk USING (company_number)
            LEFT JOIN agg_statements st USING (company_number)
            LEFT JOIN agg_cpp_ever cpp_ever USING (company_number)
            LEFT JOIN agg_cpp_active cpp_active USING (company_number)
            """
        )

        # Map the companies-per-person band ranks back to labels (private tier only); the
        # governed tier emits neither scope.
        def _band_case(rank_col: str, out_col: str) -> str:
            whens = " ".join(
                f"WHEN {rank} THEN {_sql_literal(band)}"
                for band, rank in _BAND_RANK.items()
            )
            return f"CASE {rank_col} {whens} ELSE NULL END AS {out_col}"

        if data_governance:
            select_cols = ", ".join(FEATURE_COLUMNS)
        else:
            select_cols = ", ".join(FEATURE_COLUMNS) + ", " + ", ".join((
                _band_case("_cpp_band_rank_ever", "companies_per_person_band_ever"),
                _band_case("_cpp_band_rank_active", "companies_per_person_band_active"),
            ))
        con.execute(
            f"COPY (SELECT {select_cols} FROM features) "
            f"TO {_sql_literal(str(features_path))} (FORMAT PARQUET)"
        )

        # Written-schema governance assertion: the private-linkage column must not exist
        # on disk in governed mode.
        on_disk = {row[0] for row in con.sql(
            f"DESCRIBE SELECT * FROM read_parquet({_sql_literal(str(features_path))})"
        ).fetchall()}
        if data_governance:
            leaked = sorted(on_disk & set(GOVERNED_FEATURE_DROPPED))
            if leaked:
                raise RuntimeError(
                    f"governed feature table retains person-linkage columns: {leaked}"
                )

        n_rows = con.sql(
            f"SELECT COUNT(*) FROM read_parquet({_sql_literal(str(features_path))})"
        ).fetchone()[0]
        fill = dict(con.sql(
            """SELECT 'identified', COUNT(*) FROM features
                WHERE psc_information_state = 'identified'
                UNION ALL SELECT 'statement_only', COUNT(*) FROM features
                WHERE psc_information_state = 'statement_only'
                UNION ALL SELECT 'none_reported', COUNT(*) FROM features
                WHERE psc_information_state = 'none_reported'"""
        ).fetchall())
    finally:
        con.close()

    report = {
        "snapshot_date": snapshot_date,
        "tier": mode,
        "data_governance": data_governance,
        "companies_per_person_bands": ("none in governed" if data_governance
                                       else ["ever", "active"]),
        "n_companies": n_rows,
        "information_state_counts": fill,
        "distinct_nature_sets": len(distinct_sets),
        "distinct_corporate_regnos": len(distinct_regnos),
        "outputs": {"psc_company_features": str(features_path)},
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
