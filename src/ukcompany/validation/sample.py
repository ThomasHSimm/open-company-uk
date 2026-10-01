"""Sample a fetchable positives CSV from the loaded insolvency labels.

Symmetric to the stratified control (``control.py``): this WRITES NUMBERS only -
the operator fetches them via ``ukcompany run``. The cache-only property is
preserved; no fetch path is added here.

Why a sample, not all 220k positives: the label file spans 2012-2024, and
fetching every positive is both infeasible (220k API calls) and mostly pointless
- old positives are dissolved-and-purged (404) or recovered by now, so they land
in the excluded/not-assessable buckets, not in recall. The meaningful recall test
is a few hundred RECENT adverse positives the API can still assess, plus the
existing control. This helper draws recent, adverse, capped, and deterministic.

Sampling method (documented choice): a simple seeded random sample of eligible
recent adverse positives. Case_type stratification was deliberately NOT built for
v1 - the composition print surfaces the case_type/year spread so the operator can
see it, and a simple sample keeps the step easy to reason about.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass, field
from pathlib import Path

from .labels import _VALID_MONTH, Label

# Adverse case types kept in the recall sample. "other" and any non-adverse type
# are guarded out (the publication is adverse-only already, but guard anyway).
ADVERSE_CASE_TYPES = frozenset(
    {
        "compulsory_liquidation",
        "creditors_voluntary_liquidation",
        "administration",
        "corporate_voluntary_arrangement",
    }
)


@dataclass
class PositivesSample:
    numbers: list[str] = field(default_factory=list)
    eligible: int = 0  # eligible positives before capping to N
    requested: int = 0  # N (the requested cap)
    since: str = ""
    by_case_type: dict[str, int] = field(default_factory=dict)
    by_year: dict[str, int] = field(default_factory=dict)

    @property
    def shortfall(self) -> int:
        """How many short of the requested N (0 unless fewer eligible than N)."""
        return max(0, self.requested - len(self.numbers))


def _month_at_least(month: str, since: str) -> bool:
    """True when ``month`` is a well-formed YYYY-MM at or after ``since``.

    Both are fixed-width zero-padded YYYY-MM, so lexicographic comparison is a
    correct chronological comparison. A blank or malformed month is not eligible.
    """
    return bool(_VALID_MONTH.match(month)) and month >= since


def sample_positives(labels: dict[str, Label], n: int, since: str, seed: int) -> PositivesSample:
    """Deterministically sample up to ``n`` recent adverse positives.

    Eligible = adverse ``case_type`` AND a usable ``month_registered`` >=
    ``since``. Positives lacking a usable month are excluded. If more eligible
    than ``n``, a seeded random sample of ``n`` is taken; if fewer, all are taken
    and the shortfall is reported. Deterministic given ``seed``.
    """
    eligible = sorted(
        number
        for number, label in labels.items()
        if label.case_type in ADVERSE_CASE_TYPES and _month_at_least(label.month_registered, since)
    )
    if len(eligible) <= n:
        chosen = eligible
    else:
        chosen = sorted(random.Random(seed).sample(eligible, n))

    sample = PositivesSample(numbers=chosen, eligible=len(eligible), requested=n, since=since)
    for number in chosen:
        label = labels[number]
        sample.by_case_type[label.case_type] = sample.by_case_type.get(label.case_type, 0) + 1
        year = label.month_registered[:4]
        sample.by_year[year] = sample.by_year.get(year, 0) + 1
    return sample


def write_positives_csv(sample: PositivesSample, path: str | Path) -> Path:
    """Write the sampled positive numbers as a ``company_number`` CSV.

    Same shape as the control writer / ``ukcompany run --input`` expects, so the
    operator can fetch the profiles directly. NUMBERS only - no fetch here.
    """
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["company_number"])
        for number in sample.numbers:
            writer.writerow([number])
    return output
