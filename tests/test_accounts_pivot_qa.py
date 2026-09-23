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
