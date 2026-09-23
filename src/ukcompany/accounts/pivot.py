"""Map-driven LONG-to-WIDE accounts pivot with cell-level provenance."""

from __future__ import annotations

import glob as glob_module
import json
import resource
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .core import EMPLOYEE_CONCEPT, TARGET_CONCEPTS

PivotMode = Literal["latest", "as_first_reported"]


def _peak_rss_bytes() -> int:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


@contextmanager
def track_peak_rss():
    """Yield a zero-argument callable returning peak RSS (bytes) since process start.

    Peak RSS is a monotonic high-water mark for the process lifetime, which is exact for a
    one-shot CLI invocation: no interval sampling is needed to know whether an operation
    stayed under its memory budget.
    """
    state = {"value": 0}
    try:
        yield lambda: state["value"]
    finally:
        state["value"] = _peak_rss_bytes()


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


def to_lazy(frame):
    """Accept a DataFrame or LazyFrame uniformly; converting a DataFrame is free."""
    pl = require_polars()
    return frame.lazy() if isinstance(frame, pl.DataFrame) else frame


def _mapped_cells(long_frame, mapping: WideColumnMap):
    """Reduce to only the mapped total/member cells, keeping the plan lazy.

    This filter (plus the caller's status/currency filters) is what must execute as
    predicate/projection pushdown against the source Parquet before anything is
    materialised: the mapped cells are a small fraction of the full LONG corpus.
    """
    pl = require_polars()
    totals = long_frame.filter(
        pl.col("dimension").is_null() & pl.col("concept").is_in(mapping.totals)
    ).with_columns(pl.col("concept").alias("wide_column"))
    if not mapping.members:
        return totals
    map_frame = pl.LazyFrame(
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


_CELL_COLUMNS = (
    "company",
    "period_end",
    "wide_column",
    "source_year",
    "source_month",
    "source_archive",
    "source_member",
    "made_up_to_date",
    "numeric_value",
)


def _reduce_to_cells(long_frame, mapping: WideColumnMap, mode: PivotMode):
    """Lazily reduce one frame to its mapped total/member cells, columns-projected.

    Safe to `.collect()` on a single monthly Parquet: the mapped cells are a small
    fraction of a month's rows. The explicit final `.select()` is required for real
    projection pushdown — without it the optimizer cannot prove the unused source columns
    (notably free-text `raw_value`, present on every row including non-numeric facts) are
    droppable, since it has no visibility past a `.collect()` into what happens next.
    """
    pl = require_polars()
    lazy = to_lazy(long_frame)
    if "status" in lazy.collect_schema().names():
        lazy = lazy.filter(pl.col("status") == "selected")
    usable = lazy.filter(
        (pl.col("concept") == EMPLOYEE_CONCEPT) | (pl.col("currency") == "GBP")
    )
    cells = _mapped_cells(usable, mapping)
    if mode == "as_first_reported":
        cells = cells.filter(pl.col("is_current") == 1)
    return cells.select(*_CELL_COLUMNS)


def _finalize_pivot(cells, mapping: WideColumnMap, mode: PivotMode):
    """Sort/dedupe/reshape an already-small, already-collected cells DataFrame."""
    pl = require_polars()
    descending = (
        [False, False, False, False, False, False]
        if mode == "as_first_reported"
        else [False, False, False, True, True, True]
    )
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


def pivot_long(long_frame, mapping: WideColumnMap, mode: PivotMode):
    """Return `(wide, provenance)` DataFrames without imputing absent values.

    `long_frame` may be an eager DataFrame or a LazyFrame. For a single small frame (as in
    tests, or one monthly Parquet), reduction and finalisation both happen here safely. For
    the full multi-month archive, use `pivot_long_over_parts` instead — a whole-glob lazy
    plan through this same reduction was measured to still exceed 20 GB RSS despite
    predicate/projection pushdown (Polars' streaming engine does not keep this operator
    chain — join, then sort+unique with `maintain_order=True` — bounded across a multi-file
    scan), so the safe path processes one month at a time.
    """
    mapping.validate()
    if mode not in {"latest", "as_first_reported"}:
        raise ValueError(f"unknown pivot mode: {mode}")
    cells = _reduce_to_cells(long_frame, mapping, mode).collect(engine="streaming")
    return _finalize_pivot(cells, mapping, mode)


def pivot_long_over_parts(parts: str | Path, mapping: WideColumnMap, mode: PivotMode):
    """Memory-bounded pivot over a multi-file glob: reduce each file, then finalise once.

    Peak memory scales with the largest single month's mapped-cell slice (measured at a
    few hundred MB), not with the full corpus, because each file is collected and reduced
    to `_CELL_COLUMNS` before the next file is even scanned.
    """
    pl = require_polars()
    mapping.validate()
    if mode not in {"latest", "as_first_reported"}:
        raise ValueError(f"unknown pivot mode: {mode}")
    paths = sorted(glob_module.glob(str(parts)))
    if not paths:
        raise ValueError(f"no Parquet files match: {parts}")
    reduced = [
        _reduce_to_cells(pl.scan_parquet(path), mapping, mode).collect(engine="streaming")
        for path in paths
    ]
    # Every file went through the identical `_CELL_COLUMNS` projection, so schemas match
    # exactly; "vertical" avoids diagonal_relaxed's schema-reconciliation cost.
    cells = pl.concat(reduced, how="vertical")
    return _finalize_pivot(cells, mapping, mode)


def pivot_parquet(
    long_path: str | Path,
    mapping: WideColumnMap,
    mode: PivotMode,
    wide_output: str | Path,
    provenance_output: str | Path,
) -> int:
    """Pivot the archived monthly Parquets to WIDE; returns peak RSS in bytes for this run.

    Processes one monthly Parquet at a time (see `pivot_long_over_parts`) so peak memory
    scales with the largest single month, not the full multi-month corpus.
    """
    with track_peak_rss() as peak:
        wide, provenance = pivot_long_over_parts(long_path, mapping, mode)
        Path(wide_output).parent.mkdir(parents=True, exist_ok=True)
        Path(provenance_output).parent.mkdir(parents=True, exist_ok=True)
        wide.write_parquet(wide_output, compression="zstd")
        provenance.write_parquet(provenance_output, compression="zstd")
    return peak()
