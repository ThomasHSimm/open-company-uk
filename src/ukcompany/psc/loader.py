"""PSC bulk snapshot loader: raw NDJSON parts -> queryable Parquet tables.

Per the brief (`docs/brief/psc-loader-and-page.md`, Task B): does not rely on DuckDB's
schema inference over the whole file (which samples and can drop or mistype rare keys,
e.g. super-secure or identity-verification sub-keys). Instead every part is read with
`read_ndjson_objects`, which returns one untouched JSON value per line with no inference at
all; every field this loader cares about is then pulled out explicitly by JSON path. The
full `data` object is kept as a `raw` JSON column in `--no-data-governance` mode, so any
field not yet extracted is still available.

Grain of `psc_records`: one row per input line, including malformed JSON and genuinely
unrecognised `kind` values (both land in `category = 'unknown'`, distinguished by
`n_bad_lines` in `load_report.json` rather than by a Parquet column) — this is what makes
"category counts sum to the number of lines read" a real invariant rather than an
approximation that quietly excludes the lines that are hardest to account for.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_MEMORY_LIMIT_GB = 8
DEFAULT_SPILL_DIR = "data/psc/.duckdb-spill"

PSC_REGIME_START = "2016-04-06"

# Every `kind` value observed in the real 2026-09-18 snapshot (see docs/recon-psc-results.md
# and the live shape checks behind this loader) mapped to the brief's ten categories, plus
# 'unknown' for anything else (a genuinely new kind, or malformed JSON with no kind at all).
KIND_TO_CATEGORY: dict[str, str] = {
    "individual-person-with-significant-control": "individual",
    "corporate-entity-person-with-significant-control": "corporate",
    "legal-person-person-with-significant-control": "legal_person",
    "persons-with-significant-control-statement": "statement",
    "super-secure-person-with-significant-control": "super_secure",
    "super-secure-beneficial-owner": "super_secure",
    "exemptions": "exemption",
    "individual-beneficial-owner": "bo_individual",
    "corporate-entity-beneficial-owner": "bo_corporate",
    "legal-person-beneficial-owner": "bo_legal",
    "totals#persons-of-significant-control-snapshot": "totals",
}

# The full key set of `identity_verification_details`, confirmed by scanning every one of
# the 15,952,486 lines in the 2026-09-18 snapshot (not sampled) before writing this list,
# per the brief's "first dump the distinct key paths, then extract all of them" instruction.
# `preferred_name` is a personal name despite living under this block, not under
# `name_elements` — it is dropped in --data-governance mode along with the other name
# fields, not kept as an identity-verification column.
IDENTITY_VERIFICATION_KEYS: dict[str, str] = {
    "identity_verified_on": "iv_identity_verified_on_raw",
    "appointment_verification_start_on": "iv_verification_start_on_raw",
    "appointment_verification_end_on": "iv_verification_end_on_raw",
    "appointment_verification_statement_date": "iv_verification_statement_date_raw",
    "appointment_verification_statement_due_on": "iv_verification_statement_due_on_raw",
    "authorised_corporate_service_provider_name": "iv_acsp_name",
    "anti_money_laundering_supervisory_bodies": "iv_aml_supervisory_bodies",
    "preferred_name": "iv_preferred_name",
}

NOC_SUFFIXES = (
    "-as-firm",
    "-as-trust",
    "-limited-liability-partnership",
    "-registered-overseas-entity",
)

# Matches `scripts/recon_psc.py`'s `POSTCODE_NORM_RE`, anchored for a full-string match
# against the normalised (upper-cased, whitespace-stripped) postcode. `postcode_district`
# is only ever derived from a postcode in genuine UK format; anything else (a foreign
# address, free text, a partial value) yields NULL rather than a bogus character slice.
UK_POSTCODE_NORM_RE = r"^(GIR0AA|[A-Z]{1,2}[0-9][A-Z0-9]?[0-9][A-Z]{2})$"

# Columns dropped or replaced in --data-governance mode. Kept as one place so the "no
# dropped field survives" test can assert against the same list the loader uses.
GOVERNANCE_DROPPED_COLUMNS = (
    "nationality",
    "dob_year",
    "dob_month",
    "name",
    "forename",
    "middle_name",
    "surname",
    "title",
    "iv_preferred_name",
    "address_line_1",
    "address_line_2",
    "address_premises",
    "address_locality",
    "address_region",
    "address_care_of",
    "address_po_box",
    "address_country",
    "postal_code_raw",
    "postcode_norm",
    "raw",
)


def require_duckdb():
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError("the PSC loader requires the duckdb package") from exc
    return duckdb


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _connect(memory_limit_gb: int = DEFAULT_MEMORY_LIMIT_GB, spill_dir: str = DEFAULT_SPILL_DIR):
    """A dedicated, explicitly bounded connection — see ukcompany.accounts.ooc._connect for
    why the implicit default connection does not reliably bound memory on its own."""
    duckdb = require_duckdb()
    Path(spill_dir).mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(":memory:")
    connection.execute(f"SET memory_limit = '{int(memory_limit_gb)}GB'")
    connection.execute(f"SET temp_directory = {_sql_literal(spill_dir)}")
    return connection


def _kind_category_case_sql(json_expr: str) -> str:
    when_clauses = "\n".join(
        f"        WHEN {json_expr} = {_sql_literal(kind)} THEN {_sql_literal(category)}"
        for kind, category in KIND_TO_CATEGORY.items()
    )
    return f"CASE\n{when_clauses}\n        WHEN {json_expr} IS NULL THEN 'unknown'\n        ELSE 'unknown'\n    END"


def _parsed_sql(parts_glob: str, snapshot_date: str) -> str:
    """The shared base CTE: every field pulled explicitly by JSON path, before governance.

    One row per input line, `ignore_errors=true` so a malformed line becomes a row with
    `json IS NULL` (category 'unknown') instead of aborting the whole read — the same
    "never lose a line silently" principle as the rest of this project's extractors.
    """
    parts_sql = _sql_literal(parts_glob)
    kind_expr = "d->>'kind'"
    iv_cols_sql = ",\n        ".join(
        f"d->'identity_verification_details'->>{_sql_literal(source_key)} AS {column}"
        for source_key, column in IDENTITY_VERIFICATION_KEYS.items()
        if column != "iv_aml_supervisory_bodies"
    )
    return f"""
    WITH lines AS (
        SELECT
            filename,
            row_number() OVER (PARTITION BY filename) AS line_no,
            json,
            json->'data' AS d
        FROM read_ndjson_objects({parts_sql}, filename=true, ignore_errors=true)
    ),
    parsed AS (
        SELECT
            {_sql_literal(snapshot_date)} AS snapshot_date,
            regexp_extract(filename, 'psc-snapshot-\\d{{4}}-\\d{{2}}-\\d{{2}}_(\\d+)of\\d+', 1)
                AS part,
            line_no,
            json IS NOT NULL AS line_is_valid_json,
            json->>'company_number' AS company_number,
            regexp_extract(d->'links'->>'self', '^/company/([^/]+)/', 1)
                AS company_number_from_links,
            regexp_extract(d->'links'->>'self', '([^/]+)$', 1) AS psc_id,
            {kind_expr} AS kind,
            {_kind_category_case_sql(kind_expr)} AS category,
            d->>'name' AS name,
            d->'name_elements'->>'forename' AS forename,
            d->'name_elements'->>'middle_name' AS middle_name,
            d->'name_elements'->>'surname' AS surname,
            d->'name_elements'->>'title' AS title,
            TRY_CAST(d->'date_of_birth'->>'year' AS BIGINT) AS dob_year,
            TRY_CAST(d->'date_of_birth'->>'month' AS BIGINT) AS dob_month,
            d->>'nationality' AS nationality,
            d->>'country_of_residence' AS country_of_residence,
            d->'address'->>'address_line_1' AS address_line_1,
            d->'address'->>'address_line_2' AS address_line_2,
            d->'address'->>'premises' AS address_premises,
            d->'address'->>'locality' AS address_locality,
            d->'address'->>'region' AS address_region,
            d->'address'->>'care_of' AS address_care_of,
            d->'address'->>'po_box' AS address_po_box,
            d->'address'->>'country' AS address_country,
            d->'address'->>'postal_code' AS postal_code_raw,
            upper(replace(d->'address'->>'postal_code', ' ', '')) AS postcode_norm,
            d->'identification'->>'registration_number' AS reg_number_raw,
            upper(trim(d->'identification'->>'registration_number')) AS reg_number_norm,
            d->'identification'->>'country_registered' AS country_registered,
            d->'identification'->>'legal_form' AS legal_form,
            d->'identification'->>'legal_authority' AS legal_authority,
            d->'identification'->>'place_registered' AS place_registered,
            d->>'statement' AS statement,
            TRY_CAST(d->>'is_sanctioned' AS BOOLEAN) AS is_sanctioned,
            {iv_cols_sql},
            CAST(d->'identity_verification_details'->'anti_money_laundering_supervisory_bodies'
                AS VARCHAR[]) AS iv_aml_supervisory_bodies,
            d->>'notified_on' AS notified_on_raw,
            d->>'ceased_on' AS ceased_on_raw,
            TRY_CAST(d->>'notified_on' AS DATE) AS notified_on,
            TRY_CAST(d->>'ceased_on' AS DATE) AS ceased_on,
            d->'natures_of_control' AS natures_of_control_json,
            CASE WHEN json IS NOT NULL THEN to_json(d) END AS raw
        FROM lines
    ),
    enriched AS (
        SELECT *,
            (company_number IS NOT NULL AND company_number_from_links IS NOT NULL
                AND company_number != company_number_from_links) AS company_number_mismatch,
            company_number || psc_id AS record_id,
            (ceased_on IS NOT NULL AND notified_on IS NOT NULL AND ceased_on < notified_on)
                AS f_ceased_before_notified,
            (notified_on IS NOT NULL AND notified_on < DATE {_sql_literal(PSC_REGIME_START)})
                AS f_pre_regime,
            (ceased_on IS NOT NULL
                AND (EXTRACT(year FROM ceased_on) < 2016
                     OR EXTRACT(year FROM ceased_on) > EXTRACT(year FROM DATE {_sql_literal(snapshot_date)})))
                AS f_ceased_out_of_range,
            (dob_year IS NOT NULL AND notified_on IS NOT NULL
                AND (EXTRACT(year FROM notified_on) - dob_year
                     - CASE WHEN dob_month IS NOT NULL
                            AND EXTRACT(month FROM notified_on) < dob_month
                       THEN 1 ELSE 0 END) < 16)
                AS f_age_under_16_at_notified
        FROM parsed
    )
    SELECT * FROM enriched
    """


_RECORDS_COLUMNS_PRIVATE = (
    "snapshot_date", "part", "line_no",
    "company_number", "company_number_from_links", "company_number_mismatch",
    "psc_id", "record_id",
    "kind", "category",
    "name", "forename", "middle_name", "surname", "title",
    "dob_year", "dob_month", "nationality", "country_of_residence",
    "address_line_1", "address_line_2", "address_premises", "address_locality",
    "address_region", "address_care_of", "address_po_box", "address_country",
    "postal_code_raw", "postcode_norm",
    "reg_number_raw", "reg_number_norm", "country_registered", "legal_form",
    "legal_authority", "place_registered",
    "statement", "is_sanctioned",
    "iv_identity_verified_on_raw", "iv_verification_start_on_raw",
    "iv_verification_end_on_raw", "iv_verification_statement_date_raw",
    "iv_verification_statement_due_on_raw", "iv_acsp_name",
    "iv_aml_supervisory_bodies", "iv_preferred_name",
    "notified_on_raw", "ceased_on_raw", "notified_on", "ceased_on",
    "f_ceased_before_notified", "f_pre_regime", "f_ceased_out_of_range",
    "f_age_under_16_at_notified",
    "raw",
)


def _records_select_sql(parts_glob: str, snapshot_date: str, *, data_governance: bool) -> str:
    parsed = _parsed_sql(parts_glob, snapshot_date)
    if not data_governance:
        columns_sql = ", ".join(f'"{c}"' for c in _RECORDS_COLUMNS_PRIVATE)
        return f"WITH src AS ({parsed}) SELECT {columns_sql} FROM src"

    exprs = []
    for column in _RECORDS_COLUMNS_PRIVATE:
        if column in GOVERNANCE_DROPPED_COLUMNS:
            continue
        exprs.append(f'"{column}"')
    columns_sql = ", ".join(exprs)
    # birth_band_5y replaces dob_year/dob_month; postcode_district replaces the address
    # lines and full postcode; person_key is computed here, before the name columns it
    # depends on are dropped from the SELECT list above.
    #
    # UK inward codes are always exactly 3 characters (digit + letter + letter), so once
    # the space is stripped (postcode_norm) the only reliable way to recover the outward
    # code is to drop the last 3 characters -- a regex anchored on the front (e.g.
    # `^[A-Z]{1,2}[0-9][A-Z0-9]?`) greedily eats the inward code's leading digit too, e.g.
    # "SA1 1AA" -> "SA11AA" -> wrongly extracts "SA11" instead of "SA1". `postcode_district`
    # is only derived when the full normalised postcode is valid UK format in the first
    # place (`UK_POSTCODE_NORM_RE`) -- a free-text or foreign value sliced the same way
    # would produce a plausible-looking but meaningless "district".
    #
    # `person_key` matches the recon script's base definition (forename, surname, dob
    # year+month) for direct comparability; `person_key_strict` additionally requires
    # `middle_name`, so it is only non-NULL for the ~53% of individuals with a middle name
    # recorded -- a stricter, less connective key for cases where that extra precision is
    # worth the lower coverage.
    postcode_pattern = _sql_literal(UK_POSTCODE_NORM_RE)
    return f"""
    WITH src AS ({parsed})
    SELECT {columns_sql},
        CASE WHEN dob_year IS NOT NULL THEN (dob_year - dob_year % 5) END AS birth_band_5y,
        CASE WHEN postcode_norm IS NOT NULL AND regexp_matches(postcode_norm, {postcode_pattern})
             THEN left(postcode_norm, length(postcode_norm) - 3) END AS postcode_district,
        person_key_hmac(forename, surname, dob_year, dob_month) AS person_key,
        person_key_strict_hmac(forename, middle_name, surname, dob_year, dob_month)
            AS person_key_strict
    FROM src
    """


def _noc_select_sql(parts_glob: str, snapshot_date: str) -> str:
    parsed = _parsed_sql(parts_glob, snapshot_date)
    suffix_case = "\n".join(
        f"            WHEN right_raw LIKE '%{suffix}' THEN {_sql_literal(suffix.lstrip('-'))}"
        for suffix in NOC_SUFFIXES
    )
    strip_case = "\n".join(
        f"            WHEN right_raw LIKE '%{suffix}' THEN "
        f"left(right_raw, length(right_raw) - {len(suffix)})"
        for suffix in NOC_SUFFIXES
    )
    return f"""
    WITH exploded AS (
        SELECT record_id, unnest(natures_of_control_json::VARCHAR[]) AS right_raw
        FROM ({parsed})
        WHERE natures_of_control_json IS NOT NULL
    ),
    families AS (
        SELECT record_id, right_raw,
            CASE
{suffix_case}
                ELSE 'plain'
            END AS suffix_family,
            CASE
{strip_case}
                ELSE right_raw
            END AS base_right
        FROM exploded
    )
    SELECT record_id, right_raw, base_right, suffix_family,
        regexp_extract(base_right, '(\\d+-to-\\d+-percent)', 1) AS band
    FROM families
    """


def load_psc(
    parts_glob: str,
    output_dir: str | Path,
    snapshot_date: str,
    *,
    data_governance: bool = True,
    person_key_secret: str | None = None,
    memory_limit_gb: int = DEFAULT_MEMORY_LIMIT_GB,
    spill_dir: str = DEFAULT_SPILL_DIR,
) -> dict:
    """Load one PSC snapshot into `output_dir` (default `data/psc/<snapshot_date>/`).

    Writes `psc_records.parquet`, `psc_noc.parquet`, `psc_totals.json`, and
    `load_report.json` (returned as this function's result). `data_governance=True`
    requires `person_key_secret` (the HMAC key for `person_key`) since it is the only mode
    that computes person keys at all.
    """
    if data_governance and not person_key_secret:
        raise ValueError(
            "data_governance=True requires person_key_secret (see PSC_PERSON_KEY_SECRET "
            "in .env) — person keys can only be computed with a real secret"
        )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records_path = output_dir / "psc_records.parquet"
    noc_path = output_dir / "psc_noc.parquet"
    totals_path = output_dir / "psc_totals.json"
    report_path = output_dir / "load_report.json"

    connection = _connect(memory_limit_gb, spill_dir)
    if data_governance:
        secret = person_key_secret

        def _hmac(forename, surname, year, month):
            import hashlib
            import hmac as hmac_mod

            if forename is None or surname is None or year is None or month is None:
                return None
            msg = f"{str(forename).strip().lower()}|{str(surname).strip().lower()}|{year}|{month}"
            return hmac_mod.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()

        def _hmac_strict(forename, middle_name, surname, year, month):
            import hashlib
            import hmac as hmac_mod

            if (
                forename is None
                or middle_name is None
                or surname is None
                or year is None
                or month is None
            ):
                return None
            msg = (
                f"{str(forename).strip().lower()}|{str(middle_name).strip().lower()}|"
                f"{str(surname).strip().lower()}|{year}|{month}"
            )
            return hmac_mod.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()

        connection.create_function(
            "person_key_hmac", _hmac, ["VARCHAR", "VARCHAR", "BIGINT", "BIGINT"], "VARCHAR"
        )
        connection.create_function(
            "person_key_strict_hmac",
            _hmac_strict,
            ["VARCHAR", "VARCHAR", "VARCHAR", "BIGINT", "BIGINT"],
            "VARCHAR",
        )

    try:
        records_sql = _records_select_sql(parts_glob, snapshot_date, data_governance=data_governance)
        connection.execute(
            f"COPY ({records_sql}) TO {_sql_literal(str(records_path))} "
            f"(FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        noc_sql = _noc_select_sql(parts_glob, snapshot_date)
        connection.execute(
            f"COPY ({noc_sql}) TO {_sql_literal(str(noc_path))} "
            f"(FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        n_noc = connection.sql(
            f"SELECT COUNT(*) FROM read_parquet({_sql_literal(str(noc_path))})"
        ).fetchone()[0]

        # Every report/reconciliation statistic below is computed from a fresh, always-full
        # parse (never from the just-written table) — in --data-governance mode several of
        # them (middle_name fill, the totals line) need columns that mode deliberately drops
        # from the persisted output. load_report.json is aggregates-only either way, exactly
        # like docs/recon-psc-results.json, so re-parsing for it is not a governance leak.
        stats = _parsed_sql(parts_glob, snapshot_date)
        n_lines = connection.sql(f"SELECT COUNT(*) FROM ({stats})").fetchone()[0]
        n_bad_lines = connection.sql(
            f"SELECT COUNT(*) FROM ({stats}) WHERE kind IS NULL"
        ).fetchone()[0]
        # Split by cause: `invalid_json` never parsed as JSON at all (read_ndjson_objects's
        # ignore_errors=true turned it into json IS NULL); `missing_kind` parsed fine but
        # the resulting object has no usable `kind` (e.g. no `data`, or `data` has no
        # `kind`). These are mutually exclusive and sum to n_bad_lines by construction: a
        # line with line_is_valid_json=false necessarily has kind IS NULL too, since `kind`
        # is derived from the same failed parse.
        n_bad_invalid_json, n_bad_missing_kind = connection.sql(
            f"SELECT "
            f"  COUNT(*) FILTER (WHERE NOT line_is_valid_json), "
            f"  COUNT(*) FILTER (WHERE line_is_valid_json AND kind IS NULL) "
            f"FROM ({stats})"
        ).fetchone()
        postcode_present, postcode_valid, postcode_invalid = connection.sql(
            f"SELECT "
            f"  COUNT(*) FILTER (WHERE postcode_norm IS NOT NULL), "
            f"  COUNT(*) FILTER (WHERE postcode_norm IS NOT NULL "
            f"      AND regexp_matches(postcode_norm, {_sql_literal(UK_POSTCODE_NORM_RE)})), "
            f"  COUNT(*) FILTER (WHERE postcode_norm IS NOT NULL "
            f"      AND NOT regexp_matches(postcode_norm, {_sql_literal(UK_POSTCODE_NORM_RE)})) "
            f"FROM ({stats})"
        ).fetchone()
        person_key_present, person_key_strict_present, individual_total = connection.sql(
            f"SELECT "
            f"  COUNT(*) FILTER (WHERE forename IS NOT NULL AND surname IS NOT NULL "
            f"      AND dob_year IS NOT NULL AND dob_month IS NOT NULL), "
            f"  COUNT(*) FILTER (WHERE forename IS NOT NULL AND middle_name IS NOT NULL "
            f"      AND surname IS NOT NULL AND dob_year IS NOT NULL AND dob_month IS NOT NULL), "
            f"  COUNT(*) "
            f"FROM ({stats}) WHERE category = 'individual'"
        ).fetchone()
        category_counts = dict(
            connection.sql(
                f"SELECT category, COUNT(*) FROM ({stats}) GROUP BY category ORDER BY category"
            ).fetchall()
        )
        unknown_kinds = dict(
            connection.sql(
                f"SELECT kind, COUNT(*) FROM ({stats}) "
                f"WHERE category = 'unknown' AND kind IS NOT NULL GROUP BY kind"
            ).fetchall()
        )
        company_number_mismatches = connection.sql(
            f"SELECT COUNT(*) FROM ({stats}) WHERE company_number_mismatch"
        ).fetchone()[0]
        record_id_dupes = connection.sql(
            f"SELECT COUNT(*) FROM ("
            f"  SELECT record_id, COUNT(*) AS n FROM ({stats}) "
            f"  WHERE record_id IS NOT NULL GROUP BY record_id HAVING COUNT(*) > 1"
            f")"
        ).fetchone()[0]
        psc_id_shared_across_companies = connection.sql(
            f"SELECT COUNT(*) FROM ("
            f"  SELECT psc_id, COUNT(DISTINCT company_number) AS n_companies FROM ({stats}) "
            f"  WHERE psc_id IS NOT NULL AND category NOT IN ('exemption', 'totals') "
            f"  GROUP BY psc_id HAVING COUNT(DISTINCT company_number) > 1"
            f")"
        ).fetchone()[0]
        middle_name_present, middle_name_total = connection.sql(
            f"SELECT COUNT(*) FILTER (WHERE middle_name IS NOT NULL), COUNT(*) "
            f"FROM ({stats}) WHERE category = 'individual'"
        ).fetchone()
        date_flags = connection.sql(
            f"SELECT "
            f"  COUNT(*) FILTER (WHERE f_ceased_before_notified), "
            f"  COUNT(*) FILTER (WHERE f_pre_regime), "
            f"  COUNT(*) FILTER (WHERE f_ceased_out_of_range), "
            f"  COUNT(*) FILTER (WHERE f_age_under_16_at_notified) "
            f"FROM ({stats})"
        ).fetchone()
        psc_totals = connection.sql(
            f"WITH lines AS ("
            f"    SELECT json->'data' AS d FROM read_ndjson_objects({_sql_literal(parts_glob)}, "
            f"        ignore_errors=true)"
            f") SELECT to_json(d) FROM lines "
            f"WHERE d->>'kind' = {_sql_literal('totals#persons-of-significant-control-snapshot')} "
            f"LIMIT 1"
        ).fetchone()

        # Written-output consistency check: read back what actually landed on disk and
        # compare it against the independent `stats` re-parse above. `category_counts` came
        # from `stats`, not from the Parquet file, so this is a genuine end-to-end check
        # that the COPY writes and the reconciliation numbers agree — it would catch a bug
        # where `_records_select_sql`/`_noc_select_sql` silently diverged from `_parsed_sql`
        # (e.g. a WHERE clause dropped some rows), or a corrupted/truncated write.
        written_category_counts = dict(
            connection.sql(
                f"SELECT category, COUNT(*) FROM read_parquet({_sql_literal(str(records_path))}) "
                f"GROUP BY category ORDER BY category"
            ).fetchall()
        )
        # Independently derived from `stats` via array length rather than by unnesting
        # (`_noc_select_sql`'s own method), so this doesn't just recompute the same query
        # that produced psc_noc.parquet — it cross-checks by a different mechanism.
        expected_noc_rows = connection.sql(
            f"SELECT COALESCE(SUM(len(CAST(natures_of_control_json AS VARCHAR[]))), 0) "
            f"FROM ({stats})"
        ).fetchone()[0]
        consistency_errors = []
        if written_category_counts != category_counts:
            consistency_errors.append(
                f"psc_records category counts on disk {written_category_counts} != "
                f"stats {category_counts}"
            )
        if n_noc != expected_noc_rows:
            consistency_errors.append(
                f"psc_noc row count on disk {n_noc:,} != expected from stats "
                f"{expected_noc_rows:,}"
            )
        if consistency_errors:
            raise RuntimeError(
                "PSC load consistency check failed: " + "; ".join(consistency_errors)
            )
    finally:
        connection.close()

    psc_totals_obj = json.loads(psc_totals[0]) if psc_totals and psc_totals[0] else None
    if psc_totals_obj is not None:
        Path(totals_path).write_text(json.dumps(psc_totals_obj, indent=2), encoding="utf-8")

    report = {
        "snapshot_date": snapshot_date,
        "data_governance": data_governance,
        "n_lines": n_lines,
        "n_bad_lines": n_bad_lines,
        "bad_line_reasons": {
            "invalid_json": n_bad_invalid_json,
            "missing_kind": n_bad_missing_kind,
        },
        "category_counts": category_counts,
        "categories_sum_to_lines": sum(category_counts.values()) == n_lines,
        "unknown_kinds": unknown_kinds,
        "company_number_mismatches": company_number_mismatches,
        "record_id_duplicates": record_id_dupes,
        "psc_id_shared_across_companies": psc_id_shared_across_companies,
        "middle_name_fill_individuals": {
            "key_name": "middle_name",
            "present": middle_name_present,
            "total": middle_name_total,
        },
        "postcode_format": {
            "present": postcode_present,
            "valid_uk_format": postcode_valid,
            "invalid_format": postcode_invalid,
        },
        "person_key_fill_individuals": {
            "person_key_eligible": person_key_present,
            "person_key_strict_eligible": person_key_strict_present,
            "total": individual_total,
        },
        "date_flags": {
            "f_ceased_before_notified": date_flags[0],
            "f_pre_regime": date_flags[1],
            "f_ceased_out_of_range": date_flags[2],
            "f_age_under_16_at_notified": date_flags[3],
        },
        "n_noc_assertions": n_noc,
        "consistency_check": {
            "passed": True,
            "psc_noc_row_count_expected": expected_noc_rows,
        },
        "psc_totals_line": psc_totals_obj,
        "outputs": {
            "psc_records": str(records_path),
            "psc_noc": str(noc_path),
            "psc_totals": str(totals_path) if psc_totals_obj is not None else None,
        },
    }
    Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
