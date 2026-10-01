import json
from pathlib import Path

import polars as pl
import pytest

from ukcompany.accounts.pivot import MemberColumn, WideColumnMap, load_column_map, pivot_long
from ukcompany.accounts.qa import (
    member_histogram,
    render_restatement_rate_report,
    restatement_rate_over_parts,
    total_component_reconciliation,
)


def long_frame() -> pl.DataFrame:
    defaults = {
        "dimension": None,
        "member": None,
        "currency": "GBP",
        "unit": "GBP",
        "source_archive": "archive.zip",
        "scale": 0,
        "status": "selected",
    }
    rows = [
        {
            **defaults,
            "company": "00123456",
            "period_end": "2022-12-31",
            "concept": "Equity",
            "numeric_value": "100",
            "raw_value": "100",
            "source_year": 2022,
            "source_month": 1,
            "source_member": "current.html",
            "made_up_to_date": "20221231",
            "is_current": 1,
        },
        {
            **defaults,
            "company": "00123456",
            "period_end": "2022-12-31",
            "concept": "CurrentAssets",
            "numeric_value": "50",
            "raw_value": "50",
            "currency": "EUR",
            "source_year": 2022,
            "source_month": 2,
            "source_member": "eur.html",
            "made_up_to_date": "20221231",
            "is_current": 1,
        },
        {
            **defaults,
            "company": "00123456",
            "period_end": "2022-12-31",
            "concept": "Equity",
            "numeric_value": "110",
            "raw_value": "110",
            "source_year": 2023,
            "source_month": 1,
            "source_member": "later.html",
            "made_up_to_date": "20231231",
            "is_current": 0,
        },
        {
            **defaults,
            "company": "00123456",
            "period_end": "2022-12-31",
            "concept": "CashBankOnHand",
            "numeric_value": "20",
            "raw_value": "20",
            "source_year": 2022,
            "source_month": 2,
            "source_member": "cash.html",
            "made_up_to_date": "20221231",
            "is_current": 1,
        },
        {
            **defaults,
            "company": "00123456",
            "period_end": "2022-12-31",
            "concept": "Creditors",
            "dimension": "CreditorsDimension",
            "member": "WithinOneYear",
            "numeric_value": "30",
            "raw_value": "30",
            "source_year": 2022,
            "source_month": 2,
            "source_member": "cash.html",
            "made_up_to_date": "20221231",
            "is_current": 1,
        },
        {
            **defaults,
            "company": "00123456",
            "period_end": "2022-12-31",
            "concept": "CurrentAssets",
            "numeric_value": "999",
            "raw_value": "999",
            "status": "conflict_nondimensional",
            "source_year": 2022,
            "source_month": 2,
            "source_member": "conflict.html",
            "made_up_to_date": "20221231",
            "is_current": 1,
        },
    ]
    return pl.DataFrame(rows)


def mapping() -> WideColumnMap:
    return WideColumnMap(
        ("Equity", "CashBankOnHand", "CurrentAssets"),
        (
            MemberColumn(
                "Creditors",
                "CreditorsDimension",
                "WithinOneYear",
                "creditors_within_one_year",
            ),
        ),
    )


def test_latest_and_first_reported_pivot_with_cell_provenance() -> None:
    latest, latest_provenance = pivot_long(long_frame(), mapping(), "latest")
    first, first_provenance = pivot_long(long_frame(), mapping(), "as_first_reported")

    assert latest["Equity"].item() == 110
    assert first["Equity"].item() == 100
    assert first["CurrentAssets"].item() is None
    assert first["n_concepts_present"].item() == 3
    assert first["n_source_filings"].item() == 2
    assert first["row_available_yyyymm"].item() == 202202
    assert latest["row_available_yyyymm"].item() == 202301
    assert latest_provenance.height == 3
    assert first_provenance.height == 3
    latest_equity = latest_provenance.filter(pl.col("wide_column") == "Equity").row(
        0, named=True
    )
    first_equity = first_provenance.filter(pl.col("wide_column") == "Equity").row(0, named=True)
    assert latest_equity["made_up_to_date"] == "20231231"
    assert latest_equity["period_end"] == "2022-12-31"
    assert first_equity["source_year"] == 2022


def _dash_vs_real_frame() -> pl.DataFrame:
    defaults = {
        "dimension": None,
        "member": None,
        "currency": "GBP",
        "unit": "GBP",
        "source_archive": "a.zip",
        "scale": 0,
        "status": "selected",
        "company": "00000000",
        "period_end": "2022-12-31",
        "concept": "Equity",
        "made_up_to_date": "20221231",
    }
    rows = [
        {
            **defaults,
            "numeric_value": "100",
            "raw_value": "100",
            "source_year": 2022,
            "source_month": 1,
            "source_member": "real.html",
            "is_current": 1,
        },
        {
            **defaults,
            "numeric_value": None,
            "raw_value": "-",
            "source_year": 2023,
            "source_month": 1,
            "source_member": "dash.html",
            "is_current": 0,
        },
    ]
    return pl.DataFrame(rows)


def test_dash_in_later_filing_wins_latest_as_zero(tmp_path: Path) -> None:
    """A bare dash (raw_value='-', numeric_value=None — a real, legitimate Stage 1 shape
    for a filed nil) means nil, not "no value": it competes in the ranking on equal footing
    with a real value from another filing rather than being excluded. Here the dash is the
    *later* filing, so under `latest` (most-recent-wins) it correctly overrides the earlier
    real value, in both engines — an earlier version of this fix instead excluded dash facts
    entirely, which let the real value win regardless of recency; that workaround has been
    removed in favour of treating a dash as a genuine 0."""
    from ukcompany.accounts.ooc import pivot_duckdb

    frame = _dash_vs_real_frame()
    only_totals = WideColumnMap(("Equity",), ())

    latest, latest_provenance = pivot_long(frame, only_totals, "latest")
    assert latest["Equity"].item() == 0
    assert latest_provenance["source_member"].item() == "dash.html"

    source_dir = tmp_path / "long"
    source_dir.mkdir()
    frame.write_parquet(source_dir / "accounts-long-2022-01.parquet")
    wide_output = tmp_path / "wide.parquet"
    provenance_output = tmp_path / "provenance.parquet"
    pivot_duckdb(
        str(source_dir / "*.parquet"),
        only_totals,
        "latest",
        wide_output,
        provenance_output,
        memory_limit_gb=1,
        spill_dir=str(tmp_path / "spill"),
    )
    wide = pl.read_parquet(wide_output)
    assert wide["Equity"].item() == 0
    provenance = pl.read_parquet(provenance_output)
    assert provenance.height == 1
    assert provenance["source_member"].item() == "dash.html"


def test_dash_in_original_filing_wins_as_first_reported_as_zero(tmp_path: Path) -> None:
    """A dash in the *earliest* filing wins under `as_first_reported` (earliest-wins) as a
    genuine 0, even though a later filing reports a real value — this is the case the task
    explicitly asks to prove: the original filing's dash is not skipped in favour of a later
    number, in either engine."""
    from ukcompany.accounts.ooc import pivot_duckdb

    defaults = {
        "dimension": None,
        "member": None,
        "currency": "GBP",
        "unit": "GBP",
        "source_archive": "a.zip",
        "scale": 0,
        "status": "selected",
        "company": "00000000",
        "period_end": "2022-12-31",
        "concept": "Equity",
        "made_up_to_date": "20221231",
    }
    rows = [
        {
            **defaults,
            "numeric_value": None,
            "raw_value": "-",
            "source_year": 2022,
            "source_month": 1,
            "source_member": "dash.html",
            "is_current": 1,
        },
        {
            **defaults,
            "numeric_value": "100",
            "raw_value": "100",
            "source_year": 2023,
            "source_month": 1,
            "source_member": "later.html",
            "is_current": 0,
        },
    ]
    frame = pl.DataFrame(rows)
    only_totals = WideColumnMap(("Equity",), ())

    first, first_provenance = pivot_long(frame, only_totals, "as_first_reported")
    assert first["Equity"].item() == 0
    assert first_provenance["source_member"].item() == "dash.html"

    source_dir = tmp_path / "long"
    source_dir.mkdir()
    frame.write_parquet(source_dir / "accounts-long-2022-01.parquet")
    wide_output = tmp_path / "wide.parquet"
    provenance_output = tmp_path / "provenance.parquet"
    pivot_duckdb(
        str(source_dir / "*.parquet"),
        only_totals,
        "as_first_reported",
        wide_output,
        provenance_output,
        memory_limit_gb=1,
        spill_dir=str(tmp_path / "spill"),
    )
    wide = pl.read_parquet(wide_output)
    assert wide["Equity"].item() == 0
    provenance = pl.read_parquet(provenance_output)
    assert provenance.height == 1
    assert provenance["source_member"].item() == "dash.html"


def test_column_map_is_input_and_validated(tmp_path: Path) -> None:
    path = tmp_path / "map.json"
    path.write_text(
        json.dumps(
            {
                "totals": ["Equity"],
                "members": [
                    {
                        "concept": "Creditors",
                        "dimension": "D",
                        "member": "M",
                        "column": "creditors_m",
                    }
                ],
            }
        )
    )

    loaded = load_column_map(path)

    assert loaded.columns == ("Equity", "creditors_m")
    with pytest.raises(ValueError, match="unique"):
        WideColumnMap(("Equity",), (MemberColumn("Creditors", "D", "M", "Equity"),)).validate()


def test_repository_reviewed_map_contains_only_approved_members() -> None:
    loaded = load_column_map("config/accounts-wide-columns.json")

    assert loaded.totals == (
        "Equity",
        "NetCurrentAssetsLiabilities",
        "CurrentAssets",
        "Creditors",
        "CashBankOnHand",
        "Debtors",
        "PropertyPlantEquipment",
        "TotalAssetsLessCurrentLiabilities",
        "AverageNumberEmployeesDuringPeriod",
    )
    assert loaded.members == (
        MemberColumn(
            "Equity",
            "EquityClassesDimension",
            "ShareCapital",
            "equity_share_capital",
        ),
        MemberColumn(
            "Equity",
            "EquityClassesDimension",
            "RetainedEarningsAccumulatedLosses",
            "equity_retained_earnings",
        ),
        MemberColumn(
            "Creditors",
            "MaturitiesOrExpirationPeriodsDimension",
            "WithinOneYear",
            "creditors_within_one_year",
        ),
        MemberColumn(
            "Creditors",
            "MaturitiesOrExpirationPeriodsDimension",
            "AfterOneYear",
            "creditors_after_one_year",
        ),
    )
    assert all(
        item.dimension != "RestatementsFirstTimeAdoptionDimension"
        for item in loaded.members
    )


def test_member_histogram_and_total_component_reconciliation() -> None:
    frame = long_frame()
    extra = pl.DataFrame(
        [
            {
                **frame.row(0, named=True),
                "concept": "Creditors",
                "numeric_value": "30",
                "raw_value": "30",
                "source_month": 2,
                "source_member": "cash.html",
            }
        ]
    )
    frame = pl.concat([frame, extra], how="diagonal_relaxed")

    histogram = member_histogram(frame)
    summary, comparisons = total_component_reconciliation(frame)

    assert histogram.filter(pl.col("member") == "WithinOneYear")["observations"].item() == 1
    assert comparisons.filter(pl.col("concept") == "Creditors")["agrees"].item()
    assert summary.filter(pl.col("concept") == "Creditors")["agreement_rate"].item() == 1


def test_component_reconciliation_keeps_parallel_dimensions_separate() -> None:
    frame = long_frame()
    total = {
        **frame.row(0, named=True),
        "concept": "Creditors",
        "numeric_value": "30",
        "raw_value": "30",
        "source_month": 2,
        "source_member": "cash.html",
    }
    other_axis = {
        **frame.row(4, named=True),
        "dimension": "CurrentNonCurrentDimension",
        "member": "Current",
    }
    frame = pl.concat(
        [frame, pl.DataFrame([total, other_axis])], how="diagonal_relaxed"
    )

    summary, comparisons = total_component_reconciliation(frame)

    creditor_comparisons = comparisons.filter(pl.col("concept") == "Creditors")
    assert creditor_comparisons.height == 2
    assert creditor_comparisons["agrees"].to_list() == [True, True]


def test_restatement_rate_over_parts(tmp_path: Path) -> None:
    defaults = {
        "dimension": None,
        "member": None,
        "currency": "GBP",
        "source_archive": "a.zip",
        "scale": 0,
        "status": "selected",
        "sign": None,
        "unit": "GBP",
        "fact_kind": "numeric",
        "fact_sequence": 0,
        "context_kind": "instant",
        "is_current": 1,
    }

    def fact(concept: str, value: str, *, month: int, member_html: str) -> dict:
        return {
            **defaults,
            "company": "00123456",
            "period_end": "2022-12-31",
            "concept": concept,
            "numeric_value": value,
            "raw_value": value,
            "source_year": 2022,
            "source_month": month,
            "source_member": member_html,
            "made_up_to_date": "20221231",
        }

    month1 = pl.DataFrame(
        [
            fact("Equity", "100", month=1, member_html="m1.html"),
            fact("Debtors", "50", month=1, member_html="m1.html"),
            fact("CashBankOnHand", "20", month=1, member_html="m1.html"),
        ]
    )
    month2 = pl.DataFrame(
        [
            fact("Equity", "110", month=2, member_html="m2.html"),  # disagreement
            fact("Debtors", "50", month=2, member_html="m2.html"),  # repeated, agrees
        ]
    )
    month1.write_parquet(tmp_path / "accounts-long-2022-01.parquet")
    month2.write_parquet(tmp_path / "accounts-long-2022-02.parquet")

    result = restatement_rate_over_parts(str(tmp_path / "*.parquet"), scope_label="2022 (test)")

    assert result.keys_total == 3  # Equity, Debtors, CashBankOnHand
    assert result.keys_repeated == 2  # Equity, Debtors
    assert result.keys_disagree == 1  # Equity only
    assert result.disagreement_rate == 0.5

    by_concept = {concept: (repeated, disagree) for concept, repeated, disagree in result.by_concept}
    assert by_concept["Equity"] == (1, 1)
    assert by_concept["Debtors"] == (1, 0)
    assert by_concept["CashBankOnHand"] == (0, 0)

    report = render_restatement_rate_report(result)
    assert "2022 (test)" in report
    assert "`Equity`" in report


def test_restatement_rate_duckdb_matches_python_tally(tmp_path: Path) -> None:
    """The out-of-core engine must reproduce the validated sample-scale definition exactly
    on the same data, not just approximately (see ooc.restatement_rate_duckdb)."""
    from ukcompany.accounts.ooc import restatement_rate_duckdb

    defaults = {
        "dimension": None,
        "member": None,
        "currency": "GBP",
        "source_archive": "a.zip",
        "scale": 0,
        "status": "selected",
        "sign": None,
        "unit": "GBP",
        "fact_kind": "numeric",
        "fact_sequence": 0,
        "context_kind": "instant",
        "is_current": 1,
    }

    def fact(concept: str, value: str, *, month: int, member_html: str) -> dict:
        return {
            **defaults,
            "company": "00123456",
            "period_end": "2022-12-31",
            "concept": concept,
            "numeric_value": value,
            "raw_value": value,
            "source_year": 2022,
            "source_month": month,
            "source_member": member_html,
            "made_up_to_date": "20221231",
        }

    month1 = pl.DataFrame(
        [
            fact("Equity", "100", month=1, member_html="m1.html"),
            fact("Debtors", "50", month=1, member_html="m1.html"),
            fact("CashBankOnHand", "20", month=1, member_html="m1.html"),
        ]
    )
    month2 = pl.DataFrame(
        [
            fact("Equity", "110", month=2, member_html="m2.html"),
            fact("Debtors", "50", month=2, member_html="m2.html"),
        ]
    )
    month1.write_parquet(tmp_path / "accounts-long-2022-01.parquet")
    month2.write_parquet(tmp_path / "accounts-long-2022-02.parquet")
    glob = str(tmp_path / "*.parquet")

    expected = restatement_rate_over_parts(glob, scope_label="test")
    actual = restatement_rate_duckdb(glob, scope_label="test")

    assert actual.keys_total == expected.keys_total
    assert actual.keys_repeated == expected.keys_repeated
    assert actual.keys_disagree == expected.keys_disagree
    assert actual.by_concept == expected.by_concept


def test_restatement_treats_dash_as_zero_in_both_engines(tmp_path: Path) -> None:
    """A key first reported as a dash (nil) then restated to a real number must count as
    repeated + disagree (0 != 5), in both the Python tally and the DuckDB engine — a dash
    is a genuine first-seen value of 0, not an excluded/unobserved key."""
    from ukcompany.accounts.ooc import restatement_rate_duckdb

    defaults = {
        "dimension": None,
        "member": None,
        "currency": "GBP",
        "source_archive": "a.zip",
        "scale": 0,
        "status": "selected",
        "sign": None,
        "unit": "GBP",
        "fact_kind": "numeric",
        "fact_sequence": 0,
        "context_kind": "instant",
        "is_current": 1,
        "company": "00123456",
        "period_end": "2022-12-31",
        "concept": "Equity",
    }
    month1 = pl.DataFrame(
        [{**defaults, "numeric_value": None, "raw_value": "-",
          "source_year": 2022, "source_month": 1, "source_member": "dash.html"}],
        schema_overrides={"numeric_value": pl.Utf8},
    )
    month2 = pl.DataFrame(
        [{**defaults, "numeric_value": "5", "raw_value": "5",
          "source_year": 2022, "source_month": 2, "source_member": "real.html"}]
    )
    month1.write_parquet(tmp_path / "accounts-long-2022-01.parquet")
    month2.write_parquet(tmp_path / "accounts-long-2022-02.parquet")
    glob = str(tmp_path / "*.parquet")

    expected = restatement_rate_over_parts(glob, scope_label="test")
    actual = restatement_rate_duckdb(glob, scope_label="test")

    for result in (expected, actual):
        assert result.keys_total == 1
        assert result.keys_repeated == 1
        assert result.keys_disagree == 1
    assert actual.by_concept == expected.by_concept


def test_qa_duckdb_matches_polars_qa(tmp_path: Path) -> None:
    """The out-of-core QA engine must reproduce member_histogram/total_component_
    reconciliation's results exactly on the same data (see ooc.member_histogram_duckdb,
    ooc.total_component_reconciliation_duckdb)."""
    from ukcompany.accounts.ooc import (
        member_histogram_duckdb,
        total_component_reconciliation_duckdb,
    )

    frame = long_frame()
    extra = pl.DataFrame(
        [
            {
                **frame.row(0, named=True),
                "concept": "Creditors",
                "numeric_value": "30",
                "raw_value": "30",
                "source_month": 2,
                "source_member": "cash.html",
            }
        ]
    )
    other_axis = {
        **frame.row(4, named=True),
        "dimension": "CurrentNonCurrentDimension",
        "member": "Current",
    }
    # A third, disagreeing Creditors total/component pair (different source_month/member,
    # so a separate key) makes the concept's agreement rate a genuine fraction (2/3) rather
    # than an exact 0 or 1 — this is what actually catches a DuckDB SUM() HUGEINT/Decimal
    # column dividing with integer-rounded semantics instead of true float division (a real
    # bug found in production: every rate silently rounded to 0.0% or 100.0%).
    disagree_total = {
        **frame.row(4, named=True),
        "dimension": None,
        "member": None,
        "numeric_value": "100",
        "raw_value": "100",
        "source_month": 3,
        "source_member": "q3.html",
    }
    disagree_component = {
        **frame.row(4, named=True),
        "numeric_value": "40",
        "raw_value": "40",
        "source_month": 3,
        "source_member": "q3.html",
    }
    frame = pl.concat(
        [frame, extra, pl.DataFrame([other_axis, disagree_total, disagree_component])],
        how="diagonal_relaxed",
    )
    frame.write_parquet(tmp_path / "accounts-long-2022-01.parquet")
    glob = str(tmp_path / "*.parquet")

    expected_histogram = member_histogram(frame)
    expected_summary, _expected_comparisons = total_component_reconciliation(frame)

    actual_histogram = member_histogram_duckdb(glob, memory_limit_gb=1, spill_dir=str(tmp_path / "spill"))
    actual_summary = total_component_reconciliation_duckdb(
        glob, memory_limit_gb=1, spill_dir=str(tmp_path / "spill")
    )

    expected_histogram_rows = expected_histogram.sort("concept", "dimension", "member").to_dicts()
    actual_histogram_rows = actual_histogram.sort("concept", "dimension", "member").to_dicts()
    assert actual_histogram_rows == expected_histogram_rows

    expected_summary_rows = expected_summary.sort("concept").to_dicts()
    actual_summary_rows = actual_summary.select(expected_summary.columns).sort("concept").to_dicts()
    assert actual_summary_rows == expected_summary_rows


def test_pivot_duckdb_matches_polars_pivot(tmp_path: Path) -> None:
    """The out-of-core engine must reproduce pivot_long's result exactly on the same data,
    for both modes, including provenance (see ooc.pivot_duckdb). It writes Parquet files
    directly rather than returning DataFrames, so the full cell-level provenance table
    (tens of millions of rows at full-history scale) never has to be materialised in
    Python process memory — only DuckDB's own bounded, spill-to-disk engine touches it."""
    from ukcompany.accounts.ooc import pivot_duckdb

    source_dir = tmp_path / "long"
    source_dir.mkdir()
    frame = long_frame()
    frame.write_parquet(source_dir / "accounts-long-2022-01.parquet")
    glob = str(source_dir / "*.parquet")

    for mode in ("as_first_reported", "latest"):
        expected_wide, expected_provenance = pivot_long(frame, mapping(), mode)

        wide_output = tmp_path / f"wide-{mode}.parquet"
        provenance_output = tmp_path / f"provenance-{mode}.parquet"
        pivot_duckdb(
            glob,
            mapping(),
            mode,
            wide_output,
            provenance_output,
            memory_limit_gb=1,
            spill_dir=str(tmp_path / f"spill-{mode}"),
        )
        actual_wide = pl.read_parquet(wide_output)
        actual_provenance = pl.read_parquet(provenance_output)

        expected_rows = expected_wide.sort("company", "period_end").to_dicts()
        actual_rows = actual_wide.sort("company", "period_end").to_dicts()
        assert actual_rows == expected_rows, mode

        expected_prov = expected_provenance.sort(
            "company", "period_end", "wide_column"
        ).to_dicts()
        actual_prov = actual_provenance.sort("company", "period_end", "wide_column").to_dicts()
        assert actual_prov == expected_prov, mode


def test_creditors_maturity_reconciliation_buckets(tmp_path: Path) -> None:
    """One synthetic key per bucket, exercising the priority order (incomplete_axis is
    checked before match/sign_flip/other — see ooc.creditors_maturity_reconciliation_duckdb)."""
    from ukcompany.accounts.ooc import creditors_maturity_reconciliation_duckdb

    defaults = {
        "concept": "Creditors",
        "currency": "GBP",
        "status": "selected",
        "company": "00000000",
        "period_end": "2022-12-31",
        "source_year": 2022,
        "made_up_to_date": "20221231",
        "is_current": 1,
    }

    def row(key: str, month: int, dimension, member, value: str) -> dict:
        return {
            **defaults,
            "company": key,
            "dimension": dimension,
            "member": member,
            "numeric_value": value,
            "raw_value": value,
            "source_month": month,
            "source_archive": f"{key}.zip",
            "source_member": f"{key}.html",
        }

    rows = [
        # match: 60 + 40 == 100
        row("match", 1, None, None, "100"),
        row("match", 1, "MaturitiesOrExpirationPeriodsDimension", "WithinOneYear", "60"),
        row("match", 1, "MaturitiesOrExpirationPeriodsDimension", "AfterOneYear", "40"),
        # sign_flip: -60 + -40 == -100 (negative of total)
        row("flip", 1, None, None, "100"),
        row("flip", 1, "MaturitiesOrExpirationPeriodsDimension", "WithinOneYear", "-60"),
        row("flip", 1, "MaturitiesOrExpirationPeriodsDimension", "AfterOneYear", "-40"),
        # incomplete_axis: only WithinOneYear reported
        row("incomplete", 1, None, None, "100"),
        row("incomplete", 1, "MaturitiesOrExpirationPeriodsDimension", "WithinOneYear", "60"),
        # other: 10 + 10 == 20, neither matches nor flips
        row("other", 1, None, None, "100"),
        row("other", 1, "MaturitiesOrExpirationPeriodsDimension", "WithinOneYear", "10"),
        row("other", 1, "MaturitiesOrExpirationPeriodsDimension", "AfterOneYear", "10"),
    ]
    pl.DataFrame(rows).write_parquet(tmp_path / "accounts-long-2022-01.parquet")
    glob = str(tmp_path / "*.parquet")

    summary, examples = creditors_maturity_reconciliation_duckdb(
        glob, memory_limit_gb=1, spill_dir=str(tmp_path / "spill")
    )

    counts = dict(zip(summary["bucket"].to_list(), summary["n"].to_list(), strict=True))
    assert counts == {"match": 1, "sign_flip": 1, "incomplete_axis": 1, "other": 1}
    assert summary["share"].sum() == pytest.approx(1.0)
    assert set(examples["bucket"].to_list()) == {"match", "sign_flip", "incomplete_axis", "other"}


def test_employee_unit_distribution_duckdb(tmp_path: Path) -> None:
    from ukcompany.accounts.ooc import employee_unit_distribution_duckdb

    defaults = {
        "concept": "AverageNumberEmployeesDuringPeriod",
        "dimension": None,
        "member": None,
        "currency": "GBP",
        "status": "selected",
        "company": "00000000",
        "period_end": "2022-12-31",
        "source_year": 2022,
        "source_month": 1,
        "source_archive": "a.zip",
        "made_up_to_date": "20221231",
        "is_current": 1,
    }

    def row(unit: str, value: float, member_html: str) -> dict:
        return {
            **defaults,
            "unit": unit,
            "numeric_value": str(value),
            "raw_value": str(value),
            "source_member": member_html,
        }

    # 999 plausible pure headcounts (1..999), so the 99.9th percentile lands near 999
    pure_rows = [row("pure", float(v), f"pure{v}.html") for v in range(1, 1000)]
    gbp_rows = [
        row("GBP", 5.0, "gbp-small.html"),  # a real headcount mislabelled GBP, well under cutoff
        row("GBP", 5_000_000.0, "gbp-large.html"),  # a monetary value mislabelled as headcount
    ]
    pl.DataFrame(pure_rows + gbp_rows).write_parquet(tmp_path / "accounts-long-2022-01.parquet")
    glob = str(tmp_path / "*.parquet")

    distribution, cutoff_info = employee_unit_distribution_duckdb(
        glob, memory_limit_gb=1, spill_dir=str(tmp_path / "spill")
    )

    counts = dict(zip(distribution["unit"].to_list(), distribution["n"].to_list(), strict=True))
    assert counts == {"pure": 999, "GBP": 2}
    assert cutoff_info["gbp_kept"] == 1
    assert cutoff_info["gbp_nulled"] == 1
    assert cutoff_info["cutoff"] < 5_000_000.0


def test_pivot_duckdb_keeps_all_employee_values_and_flags_gbp_tagged(tmp_path: Path) -> None:
    """No employee value is nulled or capped regardless of unit or size — an earlier cut-off
    was tried and then removed before publication (docs/accounts-employee-unit-cutoff.md).
    `employees_unit_anomaly` is still set for a GBP-tagged winning fact, diagnostic only."""
    from ukcompany.accounts.ooc import pivot_duckdb

    defaults = {
        "concept": "AverageNumberEmployeesDuringPeriod",
        "dimension": None,
        "member": None,
        "currency": "GBP",
        "status": "selected",
        "period_end": "2022-12-31",
        "source_year": 2022,
        "source_month": 1,
        "source_archive": "a.zip",
        "made_up_to_date": "20221231",
        "is_current": 1,
    }

    def row(company: str, unit: str, value: str) -> dict:
        return {
            **defaults,
            "company": company,
            "unit": unit,
            "numeric_value": value,
            "raw_value": value,
            "source_member": f"{company}.html",
        }

    rows = [
        row("large-gbp", "GBP", "5000000"),  # kept as-is, flagged
        row("small-gbp", "GBP", "50"),  # kept as-is, flagged
        row("pure", "pure", "50"),  # kept as-is, not flagged
    ]
    source_dir = tmp_path / "long"
    source_dir.mkdir()
    pl.DataFrame(rows).write_parquet(source_dir / "accounts-long-2022-01.parquet")
    glob = str(source_dir / "*.parquet")

    employee_map = WideColumnMap(("AverageNumberEmployeesDuringPeriod",), ())
    wide_output = tmp_path / "wide.parquet"
    provenance_output = tmp_path / "provenance.parquet"
    pivot_duckdb(
        glob,
        employee_map,
        "latest",
        wide_output,
        provenance_output,
        memory_limit_gb=1,
        spill_dir=str(tmp_path / "spill"),
    )

    wide = pl.read_parquet(wide_output).sort("company")
    result = {
        row["company"]: (row["AverageNumberEmployeesDuringPeriod"], row["employees_unit_anomaly"])
        for row in wide.iter_rows(named=True)
    }
    assert result["large-gbp"] == (5000000.0, 1)
    assert result["small-gbp"] == (50.0, 1)
    assert result["pure"] == (50.0, 0)


def test_restatement_rate_by_year_duckdb(tmp_path: Path) -> None:
    """Grouped by first-seen year rather than concept; a 2/3 rate in one year (not exactly
    0 or 1) is what catches a HUGEINT/Decimal-vs-float division bug (see the equivalent
    fix in total_component_reconciliation_duckdb's agreement_rate)."""
    from ukcompany.accounts.ooc import restatement_rate_by_year_duckdb

    defaults = {
        "dimension": None,
        "member": None,
        "currency": "GBP",
        "status": "selected",
        "company_period": "2022-12-31",
    }

    def fact(company: str, concept: str, value: str, *, year: int, month: int) -> dict:
        return {
            **defaults,
            "company": company,
            "period_end": "2022-12-31",
            "concept": concept,
            "numeric_value": value,
            "raw_value": value,
            "source_year": year,
            "source_month": month,
            "source_archive": f"{year}-{month}.zip",
            "source_member": f"{company}-{year}-{month}.html",
            "made_up_to_date": "20221231",
        }

    rows = [
        # first seen 2020: Equity, disagrees later (2020 -> 100 then 2021 -> 110)
        fact("a", "Equity", "100", year=2020, month=1),
        fact("a", "Equity", "110", year=2021, month=1),
        # first seen 2020: Debtors, agrees later
        fact("b", "Debtors", "50", year=2020, month=1),
        fact("b", "Debtors", "50", year=2021, month=1),
        # first seen 2020: CashBankOnHand, agrees later (third 2020 key -> 2/3 disagree rate)
        fact("c", "CashBankOnHand", "20", year=2020, month=1),
        fact("c", "CashBankOnHand", "20", year=2021, month=1),
        # first seen 2022: Equity, never repeated
        fact("d", "Equity", "200", year=2022, month=1),
    ]
    pl.DataFrame(rows).write_parquet(tmp_path / "accounts-long-2020-01.parquet")
    glob = str(tmp_path / "*.parquet")

    result = restatement_rate_by_year_duckdb(
        glob, memory_limit_gb=1, spill_dir=str(tmp_path / "spill")
    )
    by_year = {row["year"]: row for row in result.iter_rows(named=True)}

    assert by_year[2020]["keys_total"] == 3
    assert by_year[2020]["repeated"] == 3
    assert by_year[2020]["disagree"] == 1
    assert by_year[2020]["disagreement_rate"] == pytest.approx(1 / 3)
    assert by_year[2022]["keys_total"] == 1
    assert by_year[2022]["repeated"] == 0
    assert by_year[2022]["disagreement_rate"] == 0.0
