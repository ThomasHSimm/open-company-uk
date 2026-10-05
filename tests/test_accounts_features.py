"""Synthetic tests for the per-company accounts features (Handoff 02, Stage B).

All data synthetic. Covers the point-in-time rule, the zero/missing current-ratio denominator, the
>18-month-gap rule, and one case per pitfall (dash=nil, creditors maturity bucket vs total,
employees_unit_anomaly, sign). No real accounts data.
"""

import duckdb
import polars as pl

from ukcompany.accounts.features import build_accounts_features

T = 202406   # reference month: June 2024

# WIDE as_first_reported fixture (only the columns the build reads, plus Creditors to prove the
# build uses the maturity bucket, not the bare total). None => null (polars keeps null != NaN).
_COLS = ["company", "period_end", "row_available_yyyymm", "Equity", "CurrentAssets",
         "creditors_within_one_year", "Creditors", "NetCurrentAssetsLiabilities",
         "CashBankOnHand", "AverageNumberEmployeesDuringPeriod", "employees_unit_anomaly"]
_ROWS = [
    # A: two periods (12mo apart) -> deltas; negative equity; net current liabilities
    ("00000001", "2023-03-31", 202312, -500.0, 1000.0, 500.0, 9999.0, -200.0, 100.0, 5.0, 0),
    ("00000001", "2022-03-31", 202212, -300.0,  900.0, 400.0, 8888.0, -100.0,  80.0, 4.0, 0),
    # B: a 2024 period filed AFTER T (row_available 202412 > T) must be ignored at T
    ("00000002", "2023-06-30", 202312, 1000.0, 2000.0, 1000.0, 0.0, 500.0, 500.0, 20.0, 0),
    ("00000002", "2024-06-30", 202412, 9999.0, 9999.0,    1.0, 0.0, 9999.0, 9999.0, 999.0, 0),
    # C: zero denominator -> current_ratio null
    ("00000003", "2023-12-31", 202403, 50.0, 800.0, 0.0, 0.0, 10.0, 20.0, 2.0, 0),
    # D: missing denominator -> current_ratio null
    ("00000004", "2023-12-31", 202403, 60.0, 700.0, None, 0.0, 5.0, 30.0, 3.0, 0),
    # E: dash=nil => equity 0 is a declared nil (not missing, not negative)
    ("00000005", "2023-09-30", 202402, 0.0, 500.0, 200.0, 0.0, 50.0, 40.0, 1.0, 0),
    # F: GBP-tagged employee value flagged but kept; band from the value as filed
    ("00000006", "2023-01-31", 202310, 300.0, 600.0, 300.0, 0.0, 100.0, 50.0, 12.0, 1),
    # G: missing equity -> negative_equity null (missing != false)
    ("00000007", "2023-05-31", 202401, None, 400.0, 100.0, 0.0, 20.0, 10.0, 8.0, 0),
    # H: prior period >18 months before latest -> change features null
    ("00000008", "2023-12-31", 202403, 200.0, 500.0, 250.0, 0.0, 30.0, 15.0, 6.0, 0),
    ("00000008", "2021-06-30", 202112, 100.0, 400.0, 200.0, 0.0, 20.0, 10.0, 5.0, 0),
]
_REGISTER = (
    "CompanyName,CompanyNumber,Accounts.AccountCategory\n"
    "A,00000001,MICRO ENTITY\n"
    "B,00000002,TOTAL EXEMPTION FULL\n"
    "C,00000003,SMALL\n"
)


def _build(tmp_path):
    wide = tmp_path / "wide.parquet"
    pl.DataFrame(_ROWS, schema=_COLS, orient="row").write_parquet(wide)
    reg = tmp_path / "BasicCompanyData.csv"
    reg.write_text(_REGISTER, encoding="utf-8")
    report = build_accounts_features(
        wide, str(reg), tmp_path / "out", T,
        data_governance=True, memory_limit_gb=1, spill_dir=str(tmp_path / "spill"),
    )
    rows = {
        r["company_number"]: r
        for r in duckdb.sql(
            f"SELECT * FROM read_parquet('{report['outputs']['accounts_company_features']}')"
        ).df().to_dict("records")
    }
    return report, rows


def _none(v):
    return None if (v is None or (isinstance(v, float) and v != v)) else v


def test_point_in_time_excludes_later_archive(tmp_path):
    # B's 2024-06-30 period was filed after T (archive 202412); it must not affect features at T.
    _, rows = _build(tmp_path)
    b = rows["00000002"]
    assert str(b["latest_period_end"])[:10] == "2023-06-30"   # not 2024-06-30
    assert b["equity"] == 1000.0                               # not 9999
    assert b["n_periods_available"] == 1                       # the 2024 row is not counted


def test_current_ratio_null_on_zero_or_missing_denominator(tmp_path):
    _, rows = _build(tmp_path)
    assert _none(rows["00000003"]["current_ratio"]) is None    # creditors_within = 0
    assert _none(rows["00000004"]["current_ratio"]) is None    # creditors_within missing
    # and a valid one is finite (never inf): A uses the within-one-year bucket (500), not 9999
    assert rows["00000001"]["current_ratio"] == 1000.0 / 500.0


def test_creditors_maturity_bucket_not_total(tmp_path):
    # A's bare Creditors total is 9999 but the ratio uses creditors_within_one_year (500).
    _, rows = _build(tmp_path)
    assert rows["00000001"]["current_ratio"] == 2.0


def test_dash_nil_zero_is_not_missing_or_negative(tmp_path):
    _, rows = _build(tmp_path)
    d = rows["00000005"]
    assert d["equity"] == 0.0
    assert d["negative_equity"] in (False, 0)          # 0 is a declared nil, not negative
    assert _none(d["negative_equity"]) is not None     # and not null


def test_employees_unit_anomaly_kept_and_banded(tmp_path):
    _, rows = _build(tmp_path)
    e = rows["00000006"]
    assert e["employee_band"] == "11-50"               # 12 employees, Companies Act band
    assert e["employees_unit_anomaly"] == 1            # flag carried, value never dropped


def test_missing_equity_flag_is_null_not_false(tmp_path):
    _, rows = _build(tmp_path)
    assert _none(rows["00000007"]["negative_equity"]) is None   # missing != false


def test_change_features_null_across_long_gap(tmp_path):
    _, rows = _build(tmp_path)
    h = rows["00000008"]
    assert h["prior_gap_months"] == 30
    assert _none(h["d_equity"]) is None                # gap > 18 months


def test_deltas_and_flags_on_normal_company(tmp_path):
    _, rows = _build(tmp_path)
    a = rows["00000001"]
    assert a["negative_equity"] in (True, 1)           # -500 < 0 (sign respected as filed)
    assert a["net_current_liabilities"] in (True, 1)   # -200 < 0
    assert a["d_equity"] == -200.0                     # -500 - (-300)
    assert a["d_cash"] == 20.0                         # 100 - 80
    assert a["prior_gap_months"] == 12
    assert a["months_since_latest_period_end"] == 15   # (2024-2023)*12 + (6-3)
    assert a["employee_band"] == "1-10"
    assert a["accounts_category"] == "MICRO ENTITY"    # from the register, not WIDE


def test_governed_and_ungoverned_tiers_identical(tmp_path):
    # No accounts feature is person-derived, so the two tiers have the same schema.
    wide = tmp_path / "wide.parquet"
    pl.DataFrame(_ROWS, schema=_COLS, orient="row").write_parquet(wide)
    reg = tmp_path / "BasicCompanyData.csv"
    reg.write_text(_REGISTER, encoding="utf-8")
    cols = {}
    for gov in (True, False):
        rep = build_accounts_features(wide, str(reg), tmp_path / ("g" if gov else "u"), T,
                                      data_governance=gov, memory_limit_gb=1,
                                      spill_dir=str(tmp_path / "spill"))
        cols[gov] = [c[0] for c in duckdb.sql(
            f"DESCRIBE SELECT * FROM read_parquet('{rep['outputs']['accounts_company_features']}')"
        ).fetchall()]
    assert cols[True] == cols[False]
