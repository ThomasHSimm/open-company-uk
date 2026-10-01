"""Draw a stratified control cohort from the cached bulk snapshot.

A raw random control answers "how often do the flags fire in the population".
A stratified control answers the more useful question: "given companies
structurally similar to the insolvent set, do the flags still separate them?" -
stripping out the trivial confound that insolvent companies skew young and
particular-sector, so a flag could 'separate' by proxying sector or age rather
than distress.

HARD RULE: stratify ONLY on pre-distress structural confounders - SIC section
and a COARSE company-age band. Never stratify or match on anything downstream of
distress (company_status, accounts, insolvency, charges); that would control
away the very signal under test. CompanyStatus is used ONLY to define the
sampling frame (a control of already-dissolved companies is not a control) - it
is never a stratification dimension. Age is a reported covariate, banded
coarsely, never tightly matched.

This module is evaluation code: it registers nothing in FIELD_DOCS and production
scoring must never import it.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ukcompany.snapshot.loader import COLUMNS, _require_polars

from .labels import Label, sic_section_from_code

# Coarse, pre-distress age bands (a structural covariate, never a tight match).
# Day thresholds shared by the label side (Python) and the snapshot side
# (Polars) so both cohorts are banded identically. 365.25 days/year.
AGE_BANDS = ("<2y", "2-5y", "5-10y", "10y+", "UNKNOWN")
_TWO_YEARS = 730
_FIVE_YEARS = 1826
_TEN_YEARS = 3653

# Only genuinely trading companies form a valid control frame. This is an
# ELIGIBILITY filter on the frame, NOT a stratification variable.
ACTIVE_STATUSES = ("active",)

_STRATUM_SEP = "|"


def _stratum_key(section: str, band: str) -> str:
    return f"{section}{_STRATUM_SEP}{band}"


def snapshot_sic_section(text: str | None) -> str:
    """Section letter for a snapshot ``SICCode.SicText_1`` value.

    Snapshot SIC fields are text of the form ``"62012 - Business ..."`` (code
    then label), not a bare code. Parse the leading numeric code and route it
    through the SAME :func:`sic_section_from_code` used for labels, so both sides
    section identically. Blank/malformed -> ``"unknown"``.
    """
    match = re.match(r"\s*(\d+)", text or "")
    if match is None:
        return "unknown"
    return sic_section_from_code(match.group(1))


def age_band(incorporation: date | None, reference: date) -> str:
    """Coarse age band of a company at ``reference`` (never "now")."""
    if incorporation is None:
        return "UNKNOWN"
    days = (reference - incorporation).days
    if days < _TWO_YEARS:
        return "<2y"
    if days < _FIVE_YEARS:
        return "2-5y"
    if days < _TEN_YEARS:
        return "5-10y"
    return "10y+"


def _parse_month(raw: str | None) -> date | None:
    """Parse a publication ``month_registered`` proxy to a first-of-month date.

    Tolerates the common encodings without guessing: ``YYYY-MM``,
    ``YYYY-MM-DD``, ``DD/MM/YYYY`` and ``MM/YYYY``. Anything else -> ``None``
    (banded UNKNOWN), never an exception.
    """
    value = (raw or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m", "%Y-%m-%d", "%d/%m/%Y", "%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


@dataclass
class StratifiedTargets:
    """Positive-set distribution over (SIC section x coarse age band)."""

    counts: dict[str, int] = field(default_factory=dict)
    total: int = 0

    @property
    def proportions(self) -> dict[str, float]:
        if not self.total:
            return {}
        return {stratum: count / self.total for stratum, count in self.counts.items()}


def stratify_targets(labels: dict[str, Label], reference: date) -> StratifiedTargets:
    """Distribution of the positives over (SIC section x coarse age band).

    ``reference`` is the age reference date (the snapshot month), applied
    identically to positives and to the snapshot control frame.
    """
    counts: Counter[str] = Counter()
    for label in labels.values():
        band = age_band(_parse_month(label.month_registered), reference)
        counts[_stratum_key(label.sic_section, band)] += 1
    return StratifiedTargets(counts=dict(counts), total=sum(counts.values()))


@dataclass
class ControlMember:
    company_number: str
    sic_section: str
    age_band: str


@dataclass
class ControlPlan:
    """A drawn (or reloaded) stratified control and its provenance."""

    members: list[ControlMember] = field(default_factory=list)
    target_counts: dict[str, int] = field(default_factory=dict)
    achieved_counts: dict[str, int] = field(default_factory=dict)
    snapshot_month: str = ""
    frame_description: str = ""

    def numbers(self) -> list[str]:
        return [member.company_number for member in self.members]


def _frame_description(snapshot_month: str) -> str:
    return (
        "stratified on SIC section x coarse age band, drawn from the "
        f"{snapshot_month or 'cached'} snapshot, excluding positives and "
        "non-active companies"
    )


def draw_control(
    loader: Any,
    targets: StratifiedTargets,
    n: int,
    exclude: set[str],
    seed: int,
    reference: date,
    snapshot_month: str = "",
) -> ControlPlan:
    """Draw ~``n`` control company numbers mirroring ``targets``' strata.

    Deterministic given ``seed``. Filters and samples on the LazyFrame and
    collects only the drawn sample (never the full snapshot). Excludes every
    company number in ``exclude`` (the positives) and every company whose
    CompanyStatus is not an active trading status. Returns the drawn members
    plus the per-stratum target and achieved counts, so under-filled strata are
    visible.
    """
    pl = _require_polars()

    target_k = {
        stratum: round(proportion * n)
        for stratum, proportion in targets.proportions.items()
        if round(proportion * n) > 0
    }
    if not target_k:
        return ControlPlan(
            snapshot_month=snapshot_month, frame_description=_frame_description(snapshot_month)
        )

    number_col = COLUMNS["company_number"]
    status_col = COLUMNS["company_status"]
    sic_col = COLUMNS["sic_1"]
    incorporation_col = COLUMNS["incorporation_date"]

    # ONE mapping shared with the label side: build a division->section lookup
    # from the same helper, so the snapshot is sectioned identically.
    division_to_section = {f"{d:02d}": sic_section_from_code(f"{d:02d}") for d in range(1, 100)}

    section_expr = (
        pl.col(sic_col)
        .str.extract(r"(\d+)")
        .str.slice(0, 2)
        .replace_strict(division_to_section, default="unknown")
    )
    incorporation = pl.col(incorporation_col).str.to_date("%d/%m/%Y", strict=False)
    age_days = (pl.lit(reference) - incorporation).dt.total_days()
    band_expr = (
        pl.when(incorporation.is_null())
        .then(pl.lit("UNKNOWN"))
        .when(age_days < _TWO_YEARS)
        .then(pl.lit("<2y"))
        .when(age_days < _FIVE_YEARS)
        .then(pl.lit("2-5y"))
        .when(age_days < _TEN_YEARS)
        .then(pl.lit("5-10y"))
        .otherwise(pl.lit("10y+"))
    )

    # The loader guarantees clean (whitespace-stripped) column names and a
    # string-typed CompanyNumber, so no local cleanup is needed here.
    frame = (
        loader.scan()
        .select(number_col, status_col, sic_col, incorporation_col)
        .filter(
            pl.col(status_col).str.strip_chars().str.to_lowercase().is_in(list(ACTIVE_STATUSES))
        )
    )
    if exclude:
        frame = frame.filter(~pl.col(number_col).is_in(list(exclude)))

    wanted = list(target_k)
    counts_frame = pl.LazyFrame({"stratum": wanted, "k": [target_k[s] for s in wanted]})
    frame = (
        frame.with_columns(
            (section_expr + pl.lit(_STRATUM_SEP) + band_expr).alias("stratum"),
            section_expr.alias("section"),
            band_expr.alias("band"),
        )
        .filter(pl.col("stratum").is_in(wanted))
        # Deterministic per-stratum ordering by a seeded hash of the company
        # number: same seed -> same rank -> same draw.
        .with_columns(pl.col(number_col).hash(seed=seed).alias("_h"))
        .with_columns(pl.col("_h").rank(method="ordinal").over("stratum").alias("_r"))
        .join(counts_frame, on="stratum", how="inner")
        .filter(pl.col("_r") <= pl.col("k"))
        .select(number_col, "section", "band", "stratum")
    )

    drawn = frame.collect()
    members = [
        ControlMember(row[number_col], row["section"], row["band"])
        for row in drawn.sort(number_col).to_dicts()
    ]
    achieved = dict(Counter(row["stratum"] for row in drawn.to_dicts()))
    return ControlPlan(
        members=members,
        target_counts=target_k,
        achieved_counts=achieved,
        snapshot_month=snapshot_month,
        frame_description=_frame_description(snapshot_month),
    )


_CONTROL_FIELDS = ("company_number", "sic_section", "age_band")


def _sidecar_path(path: str | Path) -> Path:
    p = Path(path)
    return p.with_name(p.name + ".strata.json")


def write_control_csv(plan: ControlPlan, path: str | Path) -> Path:
    """Write the drawn numbers (with their strata) plus a provenance sidecar.

    This produces the NUMBERS only. The harness is cache-only: the operator must
    fetch these profiles (``ukcompany run --input <path>``) before their flags
    can be evaluated. No fetch happens here.
    """
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CONTROL_FIELDS)
        writer.writeheader()
        for member in plan.members:
            writer.writerow(
                {
                    "company_number": member.company_number,
                    "sic_section": member.sic_section,
                    "age_band": member.age_band,
                }
            )
    _sidecar_path(output).write_text(
        json.dumps(
            {
                "snapshot_month": plan.snapshot_month,
                "frame_description": plan.frame_description,
                "target_counts": plan.target_counts,
                "achieved_counts": plan.achieved_counts,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return output


def read_control_csv(path: str | Path) -> ControlPlan:
    """Reload a control CSV (with strata columns and sidecar, when present).

    A plain single-column list of numbers is tolerated for backward
    compatibility: such members carry section ``"unknown"`` / band ``"UNKNOWN"``
    and there is no target distribution to report.
    """
    members: list[ControlMember] = []
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header is None:
            return ControlPlan()
        header_norm = [column.strip().lower() for column in header]
        if "company_number" in header_norm:
            number_idx = header_norm.index("company_number")
            section_idx = header_norm.index("sic_section") if "sic_section" in header_norm else None
            band_idx = header_norm.index("age_band") if "age_band" in header_norm else None
        else:
            number_idx, section_idx, band_idx = 0, None, None
            if header and header[0].strip() and not header[0].strip().lower().startswith("company"):
                members.append(ControlMember(header[0].strip(), "unknown", "UNKNOWN"))
        for row in reader:
            if not row or len(row) <= number_idx or not row[number_idx].strip():
                continue
            section = row[section_idx].strip() if section_idx is not None else "unknown"
            band = row[band_idx].strip() if band_idx is not None else "UNKNOWN"
            members.append(
                ControlMember(row[number_idx].strip(), section or "unknown", band or "UNKNOWN")
            )

    plan = ControlPlan(members=members)
    sidecar = _sidecar_path(path)
    if sidecar.exists():
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        plan.snapshot_month = meta.get("snapshot_month", "")
        plan.frame_description = meta.get("frame_description", "")
        plan.target_counts = {str(k): int(v) for k, v in (meta.get("target_counts") or {}).items()}
        plan.achieved_counts = {
            str(k): int(v) for k, v in (meta.get("achieved_counts") or {}).items()
        }
    return plan
