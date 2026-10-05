"""Per-company features from the basic-company snapshot (Handoff 08, Task 2).

One row per live company in the monthly Companies House bulk file, carrying status/type/age,
SIC structure and flags, previous-name count, charge counts, accounts/confirmation-statement
state, and registered-office concentration. Where a feature also exists in
``ukcompany.derive.derive_profile`` the SAME helper is reused: ``_months_between`` for age and
``ukcompany.validation.labels.sic_section_from_code`` for the SIC section - there is no second
implementation of those rules. The heavy grouping runs in DuckDB; the shared Python helpers are
applied over the small DISTINCT vocabularies (incorporation dates, ~1k SIC codes) and joined
back, exactly as the PSC feature build does.

Reference date: the snapshot date (month-01). Every age/overdue feature is computed against it,
never against today().

Two tiers via ``data_governance`` (governed by default):
  * **governed**   - every feature except exact-address concentration.
  * **ungoverned** - adds ``n_companies_same_address`` (a per-address count; registered offices
    are sometimes home addresses, so this says something about a household).
"""

from __future__ import annotations

import glob as _glob
import json
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from ukcompany.derive import _months_between
from ukcompany.psc.loader import DEFAULT_MEMORY_LIMIT_GB, DEFAULT_SPILL_DIR, _connect, _sql_literal
from ukcompany.validation.labels import sic_section_from_code

from .loader import SnapshotLoader

# "Not elsewhere classified" SIC codes. Enumerated from the SIC-2007 condensed-list
# descriptions ending "n.e.c." as published in the Companies House basic-company data (the file
# ships the ONS SIC 2007 condensed descriptions verbatim). Source: ONS UK SIC 2007 condensed
# list, https://www.ons.gov.uk/methodology/classificationsandstandards/ukstandardindustrial
# classificationofeconomicactivities/uksic2007 . A malformed 4-digit variant ("9305") seen in
# the 2026-08 data is excluded as not a valid 5-digit SIC-2007 code.
NEC_SIC_CODES = frozenset({
    "01629", "08990", "10890", "13990", "14190", "17290", "18129", "20590", "23490",
    "23990", "25990", "28290", "28990", "30990", "32409", "32990", "33170", "42990",
    "43999", "46499", "47749", "52219", "63990", "64209", "64929", "66190", "69109",
    "74909", "77390", "79909", "82990", "85590", "87900", "88990", "93290", "94990",
    "95290", "96090",
})
DORMANT_SIC = "99999"       # "Dormant Company"
NON_TRADING_SIC = "74990"   # "Non-trading company"

# Fail the build if more than this many MALFORMED (wrong-column-count) rows are seen. A malformed
# row could be a real company with a data glitch, so the tolerance is tiny (0-5); blank lines are
# separate and allowed in any number. Malformed rows are quarantined and counted regardless.
SNAPSHOT_MAX_MALFORMED_ROWS = 5

GOVERNED_FEATURE_DROPPED = ("n_companies_same_address",)

FEATURE_COLUMNS = (
    "company_number",
    "company_status",
    "company_type",
    "date_of_creation",
    "age_months",
    "sic_sections",
    "n_sic_codes",
    "flag_dormant_sic",
    "flag_non_trading_sic",
    "flag_nec_sic",
    "n_previous_names",
    "n_charges",
    "n_charges_outstanding",
    "n_charges_part_satisfied",
    "n_charges_satisfied",
    "accounts_category",
    "accounts_next_due",
    "accounts_overdue",
    "confirmation_statement_next_due",
    "confirmation_statement_overdue",
    "accounts_never_filed",
    "n_companies_same_postcode",
)


def normalise_address(postcode: object, line1: object, *, loose: bool = False) -> str | None:
    """Normalise a registered office to (postcode + first address line) for concentration
    counting. THE single definition of address normalisation.

    Case-folded to upper; whitespace collapsed. ``loose`` removes all non-alphanumeric
    characters (maximal merging); the default removes only common punctuation (.,;:()'/-),
    a stricter match that merges fewer addresses. Returns None when both parts are empty.
    """
    combined = f"{postcode or ''} {line1 or ''}".upper()
    if loose:
        combined = re.sub(r"[^A-Z0-9]+", " ", combined)
    else:
        combined = re.sub(r"[.,;:()'/\\-]+", " ", combined)
    combined = re.sub(r"\s+", " ", combined).strip()
    return combined or None


def _col_resolver(describe_rows):
    """Map a wanted (stripped) CSV column name to its quoted actual name - the bulk file
    carries inconsistent leading whitespace on header names."""
    by_stripped = {row[0].strip(): row[0] for row in describe_rows}

    def col(name: str) -> str:
        actual = by_stripped.get(name, name)
        return '"' + actual.replace('"', '""') + '"'

    return col


def build_snapshot_features(
    parts_glob: str,
    output_dir: str | Path,
    snapshot_date: str,
    *,
    data_governance: bool = True,
    memory_limit_gb: int = DEFAULT_MEMORY_LIMIT_GB,
    spill_dir: str = DEFAULT_SPILL_DIR,
) -> dict:
    """Build the per-company snapshot feature table and write it as Parquet."""
    snap = date.fromisoformat(snapshot_date)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    mode = "governed" if data_governance else "ungoverned"
    features_path = output_dir / "snapshot_company_features.parquet"
    report_path = output_dir / "features_report.json"

    # Resolve (and if needed extract) the CSV parts via the snapshot loader - one extraction
    # definition shared with the manifest/refresh path.
    zips = sorted(_glob.glob(str(parts_glob)))
    if not zips:
        raise FileNotFoundError(f"no snapshot parts matched {parts_glob}")
    csv_paths = [str(p) for p in SnapshotLoader(zips)._csv_paths()]
    csv_list = "[" + ", ".join(_sql_literal(p) for p in csv_paths) + "]"
    # Column names from the header line, stripped (DuckDB strips the bulk file's leading-whitespace
    # headers, so the stripped names match its own column names). Parser-independent.
    import csv as _csv

    with open(csv_paths[0], newline="", encoding="utf-8", errors="replace") as _fh:
        header_names = [name.strip() for name in next(_csv.reader(_fh))]
    # store_rejects diverts every malformed (wrong-column-count) row to the reject_errors table,
    # per line, instead of silently dropping it; ignore_errors keeps the load going. The dialect
    # is pinned so there is no sniffer to choke on a malformed row in the sample. (Confirmed in
    # DuckDB 1.5.6: with a materialised read - CREATE TABLE AS SELECT - reject_errors captures
    # MISSING/TOO MANY COLUMNS per line; blank lines are skipped and are NOT rejects.)
    read_sql = (
        f"read_csv({csv_list}, header=true, all_varchar=true, delim=',', quote='\"', "
        f"escape='\"', ignore_errors=true, store_rejects=true)"
    )

    con = _connect(memory_limit_gb, spill_dir)
    try:
        con.create_function(
            "norm_addr_std",
            lambda pc, l1: normalise_address(pc, l1, loose=False),
            ["VARCHAR", "VARCHAR"], "VARCHAR",
        )
        con.create_function(
            "norm_addr_loose",
            lambda pc, l1: normalise_address(pc, l1, loose=True),
            ["VARCHAR", "VARCHAR"], "VARCHAR",
        )
        col = _col_resolver([(name,) for name in header_names])

        # --- base: one cleaned row per company, dates parsed (DD/MM/YYYY) ---
        pn_sum = " + ".join(
            f"(CASE WHEN {col(f'PreviousName_{i}.CompanyName')} IS NOT NULL "
            f"AND trim({col(f'PreviousName_{i}.CompanyName')}) <> '' THEN 1 ELSE 0 END)"
            for i in range(1, 11)
        )
        con.execute(
            f"""
            CREATE TEMP TABLE base AS
            SELECT
                trim({col('CompanyNumber')}) AS company_number,
                {col('CompanyStatus')} AS company_status,
                {col('CompanyCategory')} AS company_type,
                strptime({col('IncorporationDate')}, ['%d/%m/%Y'])::DATE AS incorp_date,
                upper(trim({col('RegAddress.PostCode')})) AS postcode,
                {col('RegAddress.AddressLine1')} AS address_line_1,
                norm_addr_std(upper(trim({col('RegAddress.PostCode')})),
                              {col('RegAddress.AddressLine1')}) AS addr_std,
                norm_addr_loose(upper(trim({col('RegAddress.PostCode')})),
                                {col('RegAddress.AddressLine1')}) AS addr_loose,
                upper(trim({col('Accounts.AccountCategory')})) AS accounts_category,
                strptime({col('Accounts.NextDueDate')}, ['%d/%m/%Y'])::DATE AS accounts_next_due,
                strptime({col('ConfStmtNextDueDate')}, ['%d/%m/%Y'])::DATE
                    AS confirmation_statement_next_due,
                TRY_CAST({col('Mortgages.NumMortCharges')} AS INTEGER) AS n_charges,
                TRY_CAST({col('Mortgages.NumMortOutstanding')} AS INTEGER)
                    AS n_charges_outstanding,
                TRY_CAST({col('Mortgages.NumMortPartSatisfied')} AS INTEGER)
                    AS n_charges_part_satisfied,
                TRY_CAST({col('Mortgages.NumMortSatisfied')} AS INTEGER) AS n_charges_satisfied,
                {col('SICCode.SicText_1')} AS sic1,
                {col('SICCode.SicText_2')} AS sic2,
                {col('SICCode.SicText_3')} AS sic3,
                {col('SICCode.SicText_4')} AS sic4,
                ({pn_sum}) AS n_previous_names
            FROM {read_sql}
            WHERE trim({col('CompanyNumber')}) IS NOT NULL
              AND trim({col('CompanyNumber')}) <> ''
            """
        )
        n_companies = con.sql("SELECT COUNT(*) FROM base").fetchone()[0]

        # No silent drops, with blanks separated from malformed rows:
        #  * MALFORMED (wrong column count) rows are captured per line by store_rejects in the
        #    reject_errors table; these are quarantined and we FAIL if they exceed a tiny
        #    threshold - a malformed row could be a real company, so we do not tolerate many.
        #  * BLANK lines are skipped by DuckDB and are NOT rejects; they are counted (via the
        #    Polars full-record count) and ALLOWED in any number.
        try:
            malformed = con.sql(
                "SELECT COUNT(DISTINCT line) FROM reject_errors"
            ).fetchone()[0]
        except Exception:
            malformed = 0  # store_rejects creates reject_errors only once a reject is seen
        quarantine_path = None
        if malformed:
            quarantine_path = str(output_dir / "malformed_rows.csv")
            con.execute(
                "COPY (SELECT DISTINCT line, error_type, csv_line FROM reject_errors "
                f"ORDER BY line) TO {_sql_literal(quarantine_path)} (FORMAT CSV, HEADER)"
            )
        # Blank / other non-company physical rows, for transparency (allowed). The Polars loader
        # counts every physical record (good + blank + malformed); subtract companies + malformed.
        import polars as pl

        n_physical = SnapshotLoader(zips).scan().select(pl.len()).collect().item()
        n_blank_or_other = n_physical - n_companies - malformed
        if malformed > SNAPSHOT_MAX_MALFORMED_ROWS:
            raise RuntimeError(
                f"snapshot feature build aborted: {malformed:,} malformed (wrong-column-count) "
                f"rows exceed the threshold of {SNAPSHOT_MAX_MALFORMED_ROWS} "
                f"(quarantined to {quarantine_path})"
            )

        # --- age via the SHARED _months_between, over distinct incorporation dates ---
        distinct_incorp = [
            row[0] for row in con.sql(
                "SELECT DISTINCT incorp_date FROM base WHERE incorp_date IS NOT NULL"
            ).fetchall()
        ]
        age_map = pd.DataFrame({
            "incorp_date": distinct_incorp,
            "age_months": [_months_between(d, snap) for d in distinct_incorp],
        })
        con.register("age_map", age_map)

        # --- SIC: long (company, code); section via the SHARED sic_section_from_code ---
        con.execute(
            """
            CREATE TEMP TABLE sic_long AS
            SELECT company_number, trim(split_part(sic, ' - ', 1)) AS code FROM (
                SELECT company_number, sic1 AS sic FROM base WHERE sic1 IS NOT NULL
                UNION ALL SELECT company_number, sic2 FROM base WHERE sic2 IS NOT NULL
                UNION ALL SELECT company_number, sic3 FROM base WHERE sic3 IS NOT NULL
                UNION ALL SELECT company_number, sic4 FROM base WHERE sic4 IS NOT NULL
            ) WHERE trim(split_part(sic, ' - ', 1)) <> ''
            """
        )
        distinct_codes = [
            row[0] for row in con.sql("SELECT DISTINCT code FROM sic_long").fetchall()
        ]
        code_section = pd.DataFrame({
            "code": distinct_codes,
            "section": [sic_section_from_code(c) for c in distinct_codes],
        })
        con.register("code_section", code_section)
        nec_list = "(" + ", ".join(_sql_literal(c) for c in sorted(NEC_SIC_CODES)) + ")"
        con.execute(
            f"""
            CREATE TEMP TABLE agg_sic AS
            SELECT s.company_number,
                   COUNT(*) AS n_sic_codes,
                   list_sort(list_distinct(list(cs.section))) AS sections,
                   bool_or(s.code = {_sql_literal(DORMANT_SIC)}) AS flag_dormant_sic,
                   bool_or(s.code = {_sql_literal(NON_TRADING_SIC)}) AS flag_non_trading_sic,
                   bool_or(s.code IN {nec_list}) AS flag_nec_sic
            FROM sic_long s
            LEFT JOIN code_section cs USING (code)
            GROUP BY s.company_number
            """
        )

        # --- registered-office concentration (postcode = governed; address = ungoverned) ---
        con.execute(
            """
            CREATE TEMP TABLE postcode_counts AS
            SELECT postcode, COUNT(*) AS n FROM base WHERE postcode IS NOT NULL
            GROUP BY postcode
            """
        )
        con.execute(
            """
            CREATE TEMP TABLE address_counts AS
            SELECT addr_std, COUNT(*) AS n FROM base WHERE addr_std IS NOT NULL
            GROUP BY addr_std
            """
        )
        # Sensitivity of the address count to the normalisation: distinct addresses under the
        # standard (stricter) vs loose (maximal-merge) rules.
        distinct_std, distinct_loose = con.sql(
            "SELECT (SELECT COUNT(*) FROM address_counts), "
            "(SELECT COUNT(DISTINCT addr_loose) FROM base WHERE addr_loose IS NOT NULL)"
        ).fetchone()

        # --- assemble ---
        con.execute(
            f"""
            CREATE TEMP TABLE features AS
            SELECT
                base.company_number,
                base.company_status,
                base.company_type,
                base.incorp_date AS date_of_creation,
                age_map.age_months,
                array_to_string(agg_sic.sections, ',') AS sic_sections,
                COALESCE(agg_sic.n_sic_codes, 0) AS n_sic_codes,
                COALESCE(agg_sic.flag_dormant_sic, FALSE) AS flag_dormant_sic,
                COALESCE(agg_sic.flag_non_trading_sic, FALSE) AS flag_non_trading_sic,
                COALESCE(agg_sic.flag_nec_sic, FALSE) AS flag_nec_sic,
                base.n_previous_names,
                base.n_charges,
                base.n_charges_outstanding,
                base.n_charges_part_satisfied,
                base.n_charges_satisfied,
                base.accounts_category,
                base.accounts_next_due,
                (base.accounts_next_due IS NOT NULL AND base.accounts_next_due < DATE {_sql_literal(snapshot_date)})
                    AS accounts_overdue,
                base.confirmation_statement_next_due,
                (base.confirmation_statement_next_due IS NOT NULL
                 AND base.confirmation_statement_next_due < DATE {_sql_literal(snapshot_date)})
                    AS confirmation_statement_overdue,
                -- Never filed = no accounts filed AND past CH's own computed next-due date
                -- (which already handles the PLC 18-month case, the 3-months-from-ARD
                -- alternative, ARD changes and extensions), not a hand-coded deadline.
                (base.accounts_category = 'NO ACCOUNTS FILED'
                 AND base.accounts_next_due IS NOT NULL
                 AND base.accounts_next_due < DATE {_sql_literal(snapshot_date)})
                    AS accounts_never_filed,
                COALESCE(pc.n, 0) AS n_companies_same_postcode,
                COALESCE(ac.n, 0) AS n_companies_same_address
            FROM base
            LEFT JOIN age_map USING (incorp_date)
            LEFT JOIN agg_sic USING (company_number)
            LEFT JOIN postcode_counts pc USING (postcode)
            LEFT JOIN address_counts ac ON base.addr_std = ac.addr_std
            """
        )

        if data_governance:
            select_cols = ", ".join(FEATURE_COLUMNS)
        else:
            select_cols = ", ".join(FEATURE_COLUMNS) + ", n_companies_same_address"
        con.execute(
            f"COPY (SELECT {select_cols} FROM features) "
            f"TO {_sql_literal(str(features_path))} (FORMAT PARQUET)"
        )

        on_disk = {row[0] for row in con.sql(
            f"DESCRIBE SELECT * FROM read_parquet({_sql_literal(str(features_path))})"
        ).fetchall()}
        if data_governance:
            leaked = sorted(on_disk & set(GOVERNED_FEATURE_DROPPED))
            if leaked:
                raise RuntimeError(
                    f"governed snapshot feature table retains address column(s): {leaked}"
                )
    finally:
        con.close()

    report = {
        "snapshot_date": snapshot_date,
        "tier": mode,
        "data_governance": data_governance,
        "n_companies": n_companies,
        "n_malformed_rows": malformed,
        "n_blank_or_other_rows": n_blank_or_other,
        "malformed_quarantine": quarantine_path,
        "address_normalisation_sensitivity": {
            "distinct_addresses_standard": distinct_std,
            "distinct_addresses_loose": distinct_loose,
        },
        "accounts_never_filed_rule": "NO ACCOUNTS FILED AND accounts_next_due < snapshot_date "
        "(CH-computed deadline)",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "outputs": {"snapshot_company_features": str(features_path)},
    }
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report
