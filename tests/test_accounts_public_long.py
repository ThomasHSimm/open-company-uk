from pathlib import Path

import polars as pl

from ukcompany.accounts.public_long import (
    NON_NUMERIC_ALLOWLIST,
    NUMERIC_DENYLIST,
    build_public_long_duckdb,
)


def defaults() -> dict:
    return {
        "company": "00123456",
        "period_end": "2022-12-31",
        "fact_sequence": 0,
        "status": "selected",
        "context_kind": "instant",
        "dimension": None,
        "member": None,
        "unit": "GBP",
        "currency": "GBP",
        "source_year": 2022,
        "source_month": 1,
        "source_archive": "a.zip",
        "source_member": "m.html",
        "made_up_to_date": "20221231",
        "scale": 0,
        "sign": None,
        "is_current": 1,
    }


def test_build_public_long_applies_denylist_and_allowlist(tmp_path: Path) -> None:
    denylisted_concept = next(iter(NUMERIC_DENYLIST))
    allowlisted_concept = next(iter(NON_NUMERIC_ALLOWLIST))
    rows = [
        {**defaults(), "concept": "Equity", "fact_kind": "numeric",
         "numeric_value": "100", "raw_value": "100"},
        {**defaults(), "concept": denylisted_concept, "fact_kind": "numeric",
         "numeric_value": "50000", "raw_value": "50000"},
        {**defaults(), "concept": allowlisted_concept, "fact_kind": "non-numeric",
         "numeric_value": None, "raw_value": "some-safe-value"},
        {**defaults(), "concept": "AddressLine1", "fact_kind": "non-numeric",
         "numeric_value": None, "raw_value": "1 Example Street"},
        {**defaults(), "concept": "EntityCurrentLegalOrRegisteredName", "fact_kind": "non-numeric",
         "numeric_value": None, "raw_value": "EXAMPLE PERSON LIMITED"},
    ]
    source_dir = tmp_path / "long"
    source_dir.mkdir()
    pl.DataFrame(rows).write_parquet(source_dir / "accounts-long-2022-01.parquet")

    output_dir = tmp_path / "public-long"
    written = build_public_long_duckdb(
        str(source_dir / "*.parquet"),
        output_dir,
        range(2022, 2023),
        memory_limit_gb=1,
        spill_dir=str(tmp_path / "spill"),
    )

    assert written == {2022: 2}
    published = pl.read_parquet(output_dir / "accounts-long-public-2022.parquet")
    concepts = set(published["concept"].to_list())
    assert concepts == {"Equity", allowlisted_concept}
    assert denylisted_concept not in concepts
    assert "AddressLine1" not in concepts
    assert "EntityCurrentLegalOrRegisteredName" not in concepts


def test_build_public_long_skips_years_with_no_source_data(tmp_path: Path) -> None:
    source_dir = tmp_path / "long"
    source_dir.mkdir()
    pl.DataFrame(
        [{**defaults(), "concept": "Equity", "fact_kind": "numeric",
          "numeric_value": "100", "raw_value": "100"}]
    ).write_parquet(source_dir / "accounts-long-2022-01.parquet")

    output_dir = tmp_path / "public-long"
    written = build_public_long_duckdb(
        str(source_dir / "*.parquet"),
        output_dir,
        range(2021, 2023),
        memory_limit_gb=1,
        spill_dir=str(tmp_path / "spill"),
    )

    assert written == {2021: 0, 2022: 1}
    assert not (output_dir / "accounts-long-public-2021.parquet").exists()
    assert (output_dir / "accounts-long-public-2022.parquet").exists()
