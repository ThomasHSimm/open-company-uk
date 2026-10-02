"""Produce small, suppressed, aggregates-only summary CSVs + static figures for the PSC site page.

Reads the loader's Parquet outputs (the maintainer's PRIVATE full load) and writes ONLY
population/per-company aggregates to ``docs/site/datasets/psc-assets/``. The site page
(`psc.qmd`) displays these committed files and executes no code, so it renders with no raw
or Parquet data present.

Two populations are reported, stated plainly on the page:
  * ALL records in the PSC product (an "ever" view: includes ceased control and dead companies);
  * LIVE companies only, i.e. those present in the Basic Company Data register. The nearest
    monthly register to the 2026-09-18 PSC snapshot is 2026-09-01 (17 days earlier) - there is no
    mid-month register product - so the live figures are as-of 2026-09-01.

Governance rules enforced here:
  * no names, no person keys, no nationality, no dates of birth in any output;
  * small counts (<10) are rendered "<10" in the CSVs BEFORE plotting, suppressed cells are never
    drawn, and each figure with drops notes how many categories were suppressed.

Run: ``python scripts/psc_site_summaries.py``. Inputs are the gitignored private load; outputs are
the small committed assets. Not imported by the package.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

LOAD_DIR = Path("data/psc/2026-09-18-stage1")
REC = str(LOAD_DIR / "psc_records.parquet")
NOC = str(LOAD_DIR / "psc_noc.parquet")
LOAD_REPORT = LOAD_DIR / "load_report.json"
PSC_TOTALS = LOAD_DIR / "psc_totals.json"
REG = "/home/tsispace/Downloads/BasicCompanyDataAsOneFile-2026-09-01.csv"
SNAPSHOT_DATE = "2026-09-18"
REG_DATE = "2026-09-01"  # nearest monthly register; 17 days before the PSC snapshot

OUT = Path("docs/site/datasets/psc-assets")
OUT.mkdir(parents=True, exist_ok=True)
SUPPRESS = 10
summary: dict = {}


def con():
    c = duckdb.connect(":memory:")
    c.execute("SET memory_limit='10GB'")
    c.execute("SET temp_directory='data/psc/.duckdb-spill'")
    c.execute("SET preserve_insertion_order=false")
    return c


def disp(n) -> str:
    return "<10" if 0 < int(n) < SUPPRESS else str(int(n))


def write_csv(name: str, header: list[str], rows: list[tuple]):
    with (OUT / name).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            *lead, n = r
            w.writerow([*lead, disp(n)])
    return [r for r in rows if int(r[-1]) >= SUPPRESS]


def snote(rows, plot):
    n = len(rows) - len(plot)
    return f"{n} categor{'y' if n == 1 else 'ies'} with <10 suppressed" if n else None


def barh(name, labels, values, title, xlabel, logx=False, note=None):
    fig, ax = plt.subplots(figsize=(8, max(2.5, 0.5 * len(labels) + 1)))
    ax.barh(range(len(labels)), values, color="#4C72B0")
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    if logx:
        ax.set_xscale("log")
    ax.set_xlabel(xlabel)
    ax.set_title(title, fontsize=10)
    if note:
        fig.text(0.01, 0.005, note, fontsize=7, color="gray")
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=110)
    plt.close(fig)


def stacked_year(name, rows, title):
    yrs = [r[0] for r in rows]
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(yrs, [r[1] for r in rows], label="active", color="#4C72B0")
    ax.bar(yrs, [r[2] for r in rows], bottom=[r[1] for r in rows], label="ceased", color="#C44E52")
    ax.set_xlabel("year control was notified (2016 regime start)")
    ax.set_ylabel("records")
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=110)
    plt.close(fig)


def write_year_csv(name, rows):
    with (OUT / name).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["year", "active", "ceased"])
        for yr, a, cc in rows:
            w.writerow([yr, disp(a), disp(cc)])


def main():
    c = con()
    report = json.loads(LOAD_REPORT.read_text())
    totals = json.loads(PSC_TOTALS.read_text())

    # Register (one read): company_number + status + incorporation date. "Live" = present in
    # the Basic Company Data register (its definition of on-the-register; dissolved companies are
    # not in the product). ignore_errors skips the one malformed CSV row.
    rc = [x[0] for x in c.sql(
        f"DESCRIBE SELECT * FROM read_csv('{REG}', header=true, all_varchar=true, "
        f"ignore_errors=true, sample_size=1)").fetchall()]
    cn = next(x for x in rc if x.strip().lower() == "companynumber")
    inc = next(x for x in rc if x.strip().lower() == "incorporationdate")
    c.execute(f"""CREATE TABLE reg AS
        SELECT trim("{cn}") AS company_number, TRY_STRPTIME("{inc}", '%d/%m/%Y')::DATE AS incd
        FROM read_csv('{REG}', header=true, all_varchar=true, ignore_errors=true)""")
    c.execute("CREATE TABLE live AS SELECT DISTINCT company_number FROM reg")
    live_total = c.sql("SELECT COUNT(*) FROM live").fetchone()[0]

    # --- Coverage box (all-product + live) ----------------------------------------------
    n_companies, n_active = c.sql(f"""
        SELECT COUNT(DISTINCT company_number),
               COUNT(DISTINCT company_number) FILTER (WHERE ceased_on_raw IS NULL
                     AND category NOT IN ('totals','exemption'))
        FROM read_parquet('{REC}')""").fetchone()
    psc_live = c.sql(f"""SELECT COUNT(DISTINCT r.company_number)
        FROM read_parquet('{REC}') r JOIN live l USING(company_number)
        WHERE r.category <> 'totals'""").fetchone()[0]
    cov = {
        "snapshot_date": SNAPSHOT_DATE,
        "register_date": REG_DATE,
        "register_gap_days": 17,
        "lines": report["n_lines"],
        "psc_records_excl_totals": report["n_lines"] - report["category_counts"].get("totals", 0),
        "distinct_companies_in_product": n_companies,
        "companies_with_active_psc_or_statement": n_active,
        "live_companies_in_register": live_total,
        "live_companies_matched_in_psc_product": psc_live,
        "totals_line_persons": totals.get("persons_of_significant_control_count"),
        "totals_line_statements": totals.get("statements_count"),
        "totals_line_exemptions": totals.get("exemptions_count"),
    }
    # Provenance: both snapshot dates are already in cov; add the generating script's identity
    # (sha256 + the repo HEAD it ran against). A file cannot contain its own commit hash, so the
    # sha256 is the verifiable link to the committed script version.
    cov["generated_by_script"] = "scripts/psc_site_summaries.py"
    cov["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    try:
        cov["generated_against_commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        cov["generated_against_commit"] = None
    write_csv("coverage.csv", ["metric", "value"],
              [(k, v) for k, v in cov.items() if isinstance(v, int)])
    (OUT / "coverage.json").write_text(json.dumps(cov, indent=1), encoding="utf-8")
    summary["coverage"] = cov

    # --- 1. records by kind -------------------------------------------------------------
    rows = c.sql(f"""SELECT category, COUNT(*) n FROM read_parquet('{REC}')
        WHERE category <> 'totals' GROUP BY category ORDER BY n DESC""").fetchall()
    plot = write_csv("01_records_by_kind.csv", ["kind", "records"], rows)
    barh("01_records_by_kind.png", [r[0] for r in plot], [r[1] for r in plot],
         "PSC records by kind (log scale)", "records (log)", logx=True, note=snote(rows, plot))
    summary["01_records_by_kind"] = rows

    # --- 2. active vs ceased (all + live) -----------------------------------------------
    for suffix, join in (("", ""), ("_live", "JOIN live l USING(company_number)")):
        rows = c.sql(f"""SELECT CASE WHEN ceased_on_raw IS NULL THEN 'active' ELSE 'ceased' END status,
            COUNT(*) n FROM read_parquet('{REC}') r {join}
            WHERE category <> 'totals' GROUP BY status ORDER BY n DESC""").fetchall()
        plot = write_csv(f"02_active_vs_ceased{suffix}.csv", ["status", "records"], rows)
        ttl = "active vs ceased" + (" (live companies, as of 2026-09-01)" if suffix else " (all records, ever)")
        barh(f"02_active_vs_ceased{suffix}.png", [r[0] for r in plot], [r[1] for r in plot],
             f"PSC records: {ttl}", "records", note=snote(rows, plot))
        summary[f"02_active_vs_ceased{suffix}"] = rows

    # --- 3. nature-of-control cores -----------------------------------------------------
    rows = c.sql(f"""SELECT COALESCE(core,'empty nature value') core, COUNT(*) n
        FROM read_parquet('{NOC}') GROUP BY core ORDER BY n DESC""").fetchall()
    plot = write_csv("03_noc_cores.csv", ["core_right", "assertions"], rows)
    barh("03_noc_cores.png", [r[0] for r in plot], [r[1] for r in plot],
         "Nature-of-control assertions by core right (log)", "assertions (log)",
         logx=True, note=snote(rows, plot))
    summary["03_noc_cores"] = rows

    # --- 4. PSC information state per company (all + live) -------------------------------
    for suffix, join in (("", ""), ("_live", "JOIN live l USING(company_number)")):
        rows = c.sql(f"""
            WITH per AS (
              SELECT r.company_number,
                bool_or(ceased_on_raw IS NULL AND category IN
                  ('individual','corporate','legal_person','super_secure',
                   'bo_individual','bo_corporate','bo_legal')) AS has_active_psc,
                bool_or(ceased_on_raw IS NULL AND category='statement') AS has_active_stmt
              FROM read_parquet('{REC}') r {join}
              WHERE category <> 'totals' GROUP BY r.company_number
            )
            SELECT CASE WHEN has_active_psc THEN 'identified'
                        WHEN has_active_stmt THEN 'statement_only'
                        ELSE 'ceased_only_or_none_active' END state, COUNT(*) n
            FROM per GROUP BY state ORDER BY n DESC""").fetchall()
        plot = write_csv(f"04_info_state_per_company{suffix}.csv", ["state", "companies"], rows)
        ttl = "(live companies, as of 2026-09-01)" if suffix else "(companies in the PSC product)"
        barh(f"04_info_state_per_company{suffix}.png", [r[0] for r in plot], [r[1] for r in plot],
             f"PSC information state per company {ttl}", "companies", logx=True, note=snote(rows, plot))
        summary[f"04_info_state_per_company{suffix}"] = rows

    # --- 8. control-start year, active vs ceased (all + live) ---------------------------
    for suffix, join in (("", ""), ("_live", "JOIN live l USING(company_number)")):
        rows = c.sql(f"""SELECT EXTRACT(year FROM notified_on)::INT yr,
               COUNT(*) FILTER (WHERE ceased_on_raw IS NULL) active,
               COUNT(*) FILTER (WHERE ceased_on_raw IS NOT NULL) ceased
            FROM read_parquet('{REC}') r {join}
            WHERE category <> 'totals' AND notified_on IS NOT NULL
              AND EXTRACT(year FROM notified_on) BETWEEN 2016 AND 2026
            GROUP BY yr ORDER BY yr""").fetchall()
        write_year_csv(f"08_control_start_year{suffix}.csv", rows)
        ttl = "(live companies, as of 2026-09-01)" if suffix else "(all records, ever)"
        stacked_year(f"08_control_start_year{suffix}.png", rows,
                     f"Records by year control started, active vs ceased {ttl}")
        summary[f"08_control_start_year{suffix}"] = rows

    # --- 9. active statement codes ------------------------------------------------------
    rows = c.sql(f"""SELECT statement, COUNT(*) n FROM read_parquet('{REC}')
        WHERE category='statement' AND ceased_on_raw IS NULL AND statement IS NOT NULL
        GROUP BY statement ORDER BY n DESC""").fetchall()
    plot = write_csv("09_active_statement_codes.csv", ["statement_code", "records"], rows)
    barh("09_active_statement_codes.png", [r[0] for r in plot], [r[1] for r in plot],
         "Active statement codes (log)", "records (log)", logx=True, note=snote(rows, plot))
    summary["09_active_statement_codes"] = rows

    # --- 7. ECCTA identity-verification counts (as of snapshot; rollout ongoing) ---------
    vrow = c.sql(f"""SELECT
        COUNT(*) FILTER (WHERE iv_identity_verified_on_raw IS NOT NULL) verified,
        COUNT(*) FILTER (WHERE iv_verification_statement_date_raw IS NOT NULL) stmt_filed,
        COUNT(*) FILTER (WHERE iv_verification_start_on_raw IS NOT NULL) start_present,
        COUNT(*) n_individual
        FROM read_parquet('{REC}') WHERE category='individual'""").fetchone()
    vrows = [("verification_start_on present", vrow[2]),
             ("verification_statement_date present", vrow[1]),
             ("identity_verified_on present", vrow[0])]
    plot = write_csv("07_eccta_verification.csv", ["measure", "individuals"], vrows)
    barh("07_eccta_verification.png", [r[0] for r in plot], [r[1] for r in plot],
         f"ECCTA identity-verification of {vrow[3]:,} individuals (as of snapshot; rollout ongoing)",
         "individuals", note=snote(vrows, plot))
    summary["07_eccta_verification"] = {"counts": vrows, "n_individual": vrow[3]}

    # --- 5. notification lag (KEPT as script output; NOT shown on the page this pass) ----
    rows = c.sql(f"""
        WITH j AS (
          SELECT (r.notified_on - reg.incd) AS lag_days
          FROM read_parquet('{REC}') r JOIN reg ON r.company_number = reg.company_number
          WHERE r.category <> 'totals' AND r.notified_on IS NOT NULL
            AND reg.incd IS NOT NULL AND reg.incd >= DATE '2016-04-06')
        SELECT CASE
                 WHEN lag_days < 0 THEN '1 before incorporation (dirty)'
                 WHEN lag_days <= 7 THEN '2 <= 7 days'
                 WHEN lag_days <= 30 THEN '3 8-30 days'
                 WHEN lag_days <= 365 THEN '4 1-12 months'
                 WHEN lag_days <= 1825 THEN '5 1-5 years'
                 ELSE '6 5+ years' END bin, COUNT(*) n
        FROM j GROUP BY bin ORDER BY bin""").fetchall()
    write_csv("05_notification_lag.csv", ["lag_bin", "records"], rows)
    summary["05_notification_lag"] = rows  # kept; notified_on semantics are a follow-up

    # --- 6. companies-per-person bands, both keys, active-only AND ever ------------------
    c.execute(f"""CREATE TABLE ind AS
      SELECT company_number, ceased_on_raw,
        lower(trim(forename))||'|'||lower(trim(surname))||'|'||dob_year||'|'||dob_month AS bkey,
        lower(trim(forename))||'|'||lower(trim(surname)) AS nm,
        CASE WHEN middle_name IS NOT NULL AND trim(middle_name)<>'' THEN
          lower(trim(forename))||'|'||lower(trim(middle_name))||'|'||lower(trim(surname))||'|'||dob_year||'|'||dob_month END AS skey
      FROM read_parquet('{REC}')
      WHERE category='individual' AND forename IS NOT NULL AND surname IS NOT NULL
        AND dob_year IS NOT NULL AND dob_month IS NOT NULL""")
    c.execute("CREATE TABLE namec AS SELECT nm, COUNT(DISTINCT bkey) n_people FROM ind GROUP BY nm")
    BAND = ("CASE WHEN n_people=1 THEN 'unique name' WHEN n_people<=10 THEN '2-10' "
            "WHEN n_people<=100 THEN '11-100' ELSE '101+' END")

    def bands(keycol, scope_where):
        c.execute("DROP TABLE IF EXISTS kc")
        c.execute(f"""CREATE TABLE kc AS
          SELECT {keycol} AS k, any_value(nm) AS nm, COUNT(DISTINCT company_number) n_co
          FROM ind WHERE {keycol} IS NOT NULL {scope_where} GROUP BY {keycol}""")
        return c.sql(f"""SELECT {BAND} band, COUNT(*) n_keys,
           round(100.0*AVG((n_co>=2)::int),3) pct_ge2, round(100.0*AVG((n_co>=11)::int),4) pct_ge11
           FROM kc JOIN namec USING(nm) GROUP BY band ORDER BY MIN(n_people)""").fetchall()

    combos = {"baseline_ever": ("bkey", ""), "baseline_active": ("bkey", "AND ceased_on_raw IS NULL"),
              "strict_ever": ("skey", ""), "strict_active": ("skey", "AND ceased_on_raw IS NULL")}
    cpp = {name: bands(col, where) for name, (col, where) in combos.items()}
    with (OUT / "06_companies_per_person_bands.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["key", "scope", "name_band", "keys", "pct_2plus_companies", "pct_11plus_companies"])
        for name, res in cpp.items():
            key, scope = name.split("_")
            for band, n_keys, p2, p11 in res:
                w.writerow([key, scope, band, disp(n_keys), p2, p11])
    all_bands = ["unique name", "2-10", "11-100", "101+"]
    series = {}
    for name, res in cpp.items():
        d = {b: (p11 if nk >= SUPPRESS else None) for (b, nk, p2, p11) in res}
        series[name] = [d.get(b) or 0 for b in all_bands]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    x = np.arange(len(all_bands))
    w = 0.8 / len(series)
    for i, (lbl, vals) in enumerate(series.items()):
        ax.bar(x + i * w, vals, w, label=lbl)
    ax.set_xticks(x + 0.4 - w / 2)
    ax.set_xticklabels(all_bands)
    ax.set_xlabel("name-frequency band (distinct baseline keys sharing a forename+surname)")
    ax.set_ylabel("% of keys on >=11 companies")
    ax.set_title("Share of person-keys on >=11 companies, by name-frequency band", fontsize=10)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "06_companies_per_person_bands.png", dpi=110)
    plt.close(fig)
    summary["06_companies_per_person_bands"] = cpp

    c.close()
    print(json.dumps(summary, default=str, indent=1))


if __name__ == "__main__":
    main()
