import importlib.util
import sys
from pathlib import Path

import polars as pl
import pytest

_SPEC = importlib.util.spec_from_file_location(
    "kaggle_staging_guard",
    Path(__file__).resolve().parent.parent / "scripts" / "kaggle_staging_guard.py",
)
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules["kaggle_staging_guard"] = _MODULE
_SPEC.loader.exec_module(_MODULE)

scan_directory = _MODULE.scan_directory
NUMERIC_DENYLIST = _MODULE.NUMERIC_DENYLIST
NON_NUMERIC_ALLOWLIST = _MODULE.NON_NUMERIC_ALLOWLIST


@pytest.fixture
def connection():
    duckdb = _MODULE.require_duckdb()
    con = duckdb.connect(":memory:")
    yield con
    con.close()


def long_row(concept: str, fact_kind: str) -> dict:
    return {
        "company": "00000000",
        "period_end": "2022-12-31",
        "concept": concept,
        "fact_kind": fact_kind,
        "numeric_value": "1" if fact_kind == "numeric" else None,
        "raw_value": "1",
    }


def test_clean_long_shaped_directory_passes(tmp_path: Path, connection) -> None:
    allowed_non_numeric = next(iter(NON_NUMERIC_ALLOWLIST))
    pl.DataFrame(
        [long_row("Equity", "numeric"), long_row(allowed_non_numeric, "non-numeric")]
    ).write_parquet(tmp_path / "accounts-long-public-2022.parquet")

    violations = scan_directory(connection, tmp_path)
    assert violations == []


def test_denylisted_numeric_concept_is_caught(tmp_path: Path, connection) -> None:
    denylisted = next(iter(NUMERIC_DENYLIST))
    pl.DataFrame(
        [long_row("Equity", "numeric"), long_row(denylisted, "numeric")]
    ).write_parquet(tmp_path / "accounts-long-public-2022.parquet")

    violations = scan_directory(connection, tmp_path)
    assert any(denylisted in v for v in violations)


def test_non_allowlisted_non_numeric_concept_is_caught(tmp_path: Path, connection) -> None:
    pl.DataFrame(
        [long_row("Equity", "numeric"), long_row("AddressLine1", "non-numeric")]
    ).write_parquet(tmp_path / "accounts-long-public-2022.parquet")

    violations = scan_directory(connection, tmp_path)
    assert any("AddressLine1" in v for v in violations)


def test_company_name_concept_is_always_forbidden(tmp_path: Path, connection) -> None:
    pl.DataFrame(
        [long_row("EntityCurrentLegalOrRegisteredName", "non-numeric")]
    ).write_parquet(tmp_path / "accounts-long-public-2022.parquet")

    violations = scan_directory(connection, tmp_path)
    assert any("EntityCurrentLegalOrRegisteredName" in v for v in violations)


def test_clean_wide_shaped_file_passes(tmp_path: Path, connection) -> None:
    pl.DataFrame(
        [{"company": "00000000", "period_end": "2022-12-31", "Equity": 100.0,
          "n_concepts_present": 1, "n_source_filings": 1, "row_available_yyyymm": 202201}]
    ).write_parquet(tmp_path / "accounts-wide-as_first_reported.parquet")

    violations = scan_directory(connection, tmp_path)
    assert violations == []


def test_wide_file_with_a_denylisted_column_is_caught(tmp_path: Path, connection) -> None:
    denylisted = next(iter(NUMERIC_DENYLIST))
    pl.DataFrame(
        [{"company": "00000000", "period_end": "2022-12-31", "Equity": 100.0, denylisted: 1.0}]
    ).write_parquet(tmp_path / "accounts-wide-as_first_reported.parquet")

    violations = scan_directory(connection, tmp_path)
    assert any(denylisted in v for v in violations)


def test_empty_directory_is_a_violation(tmp_path: Path, connection) -> None:
    violations = scan_directory(connection, tmp_path)
    assert any("no Parquet files" in v for v in violations)
