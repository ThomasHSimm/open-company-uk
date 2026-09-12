"""Map-driven LONG-to-WIDE accounts pivot with cell-level provenance."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .core import EMPLOYEE_CONCEPT, TARGET_CONCEPTS

PivotMode = Literal["latest", "as_first_reported"]


@dataclass(frozen=True)
class MemberColumn:
    concept: str
    dimension: str
    member: str
    column: str


@dataclass(frozen=True)
class WideColumnMap:
    totals: tuple[str, ...]
    members: tuple[MemberColumn, ...]

    def validate(self) -> None:
        unknown = set(self.totals) - set(TARGET_CONCEPTS)
        if unknown:
            raise ValueError(f"unknown total concept(s): {', '.join(sorted(unknown))}")
        columns = [*self.totals, *(item.column for item in self.members)]
        if len(columns) != len(set(columns)):
            raise ValueError("wide column names must be unique")
        for item in self.members:
            if item.concept not in TARGET_CONCEPTS:
                raise ValueError(f"unknown member concept: {item.concept}")
            if not item.dimension or not item.member or not item.column:
                raise ValueError("member mappings require dimension, member, and column")

    @property
    def columns(self) -> tuple[str, ...]:
        return (*self.totals, *(item.column for item in self.members))


def load_column_map(path: str | Path) -> WideColumnMap:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    mapping = WideColumnMap(
        tuple(raw.get("totals", [])),
        tuple(MemberColumn(**item) for item in raw.get("members", [])),
    )
    mapping.validate()
    return mapping


def require_polars():
    try:
        import polars as pl
    except ImportError as exc:
        raise RuntimeError("accounts pivot requires the project's dev extra (polars)") from exc
    return pl


def _mapped_cells(long_frame, mapping: WideColumnMap):
    pl = require_polars()
    totals = long_frame.filter(
        pl.col("dimension").is_null() & pl.col("concept").is_in(mapping.totals)
    ).with_columns(pl.col("concept").alias("wide_column"))
    if not mapping.members:
        return totals
    map_frame = pl.DataFrame(
        [
            {
                "concept": item.concept,
                "dimension": item.dimension,
                "member": item.member,
                "wide_column": item.column,
            }
            for item in mapping.members
        ]
    )
    members = long_frame.filter(pl.col("dimension").is_not_null()).join(
        map_frame, on=["concept", "dimension", "member"], how="inner"
    )
    return pl.concat([totals, members], how="diagonal_relaxed")


def pivot_long(long_frame, mapping: WideColumnMap, mode: PivotMode):
    """Return `(wide, provenance)` DataFrames without imputing absent values."""
    pl = require_polars()
    mapping.validate()
    if mode not in {"latest", "as_first_reported"}:
        raise ValueError(f"unknown pivot mode: {mode}")
    usable = long_frame.filter(
        (pl.col("concept") == EMPLOYEE_CONCEPT) | (pl.col("currency") == "GBP")
    )
    cells = _mapped_cells(usable, mapping)
    if mode == "as_first_reported":
        cells = cells.filter(pl.col("is_current") == 1)
        descending = [False, False, False, False, False, False]
    else:
        descending = [False, False, False, True, True, True]
    cells = (
        cells.sort(
            [
                "company",
                "period_end",
                "wide_column",
                "source_year",
                "source_month",
                "source_member",
            ],
            descending=descending,
        )
        .unique(
            subset=["company", "period_end", "wide_column"],
            keep="first",
            maintain_order=True,
        )
        .with_columns(pl.col("numeric_value").cast(pl.Float64, strict=False))
    )
    provenance = cells.select(
        "company",
        "period_end",
        "wide_column",
        "source_year",
        "source_month",
        "source_member",
        "made_up_to_date",
    ).sort("company", "period_end", "wide_column")
    summary = cells.group_by("company", "period_end").agg(
        pl.col("wide_column").n_unique().alias("n_concepts_present"),
        pl.struct("source_year", "source_month", "source_archive", "source_member")
        .n_unique()
        .alias("n_source_filings"),
        (pl.col("source_year") * 100 + pl.col("source_month"))
        .max()
        .alias("row_available_yyyymm"),
    )
    wide = cells.pivot(
        on="wide_column",
        index=["company", "period_end"],
        values="numeric_value",
        aggregate_function="first",
    )
    for column in mapping.columns:
        if column not in wide.columns:
            wide = wide.with_columns(pl.lit(None, dtype=pl.Float64).alias(column))
    wide = wide.join(summary, on=["company", "period_end"], how="left").select(
        "company",
        "period_end",
        *mapping.columns,
        "n_concepts_present",
        "n_source_filings",
        "row_available_yyyymm",
    )
    return wide.sort("company", "period_end"), provenance


def pivot_parquet(
    long_path: str | Path,
    mapping: WideColumnMap,
    mode: PivotMode,
    wide_output: str | Path,
    provenance_output: str | Path,
) -> None:
    pl = require_polars()
    frame = pl.read_parquet(long_path)
    wide, provenance = pivot_long(frame, mapping, mode)
    Path(wide_output).parent.mkdir(parents=True, exist_ok=True)
    Path(provenance_output).parent.mkdir(parents=True, exist_ok=True)
    wide.write_parquet(wide_output, compression="zstd")
    provenance.write_parquet(provenance_output, compression="zstd")
