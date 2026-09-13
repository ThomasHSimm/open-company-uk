"""Report-only concept inventory and read-correctness audits for Stage 1 facts."""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

INVENTORY_COLUMNS = (
    "concept",
    "observations",
    "companies",
    "kind",
    "units",
    "context_kind",
    "pct_numeric_null",
    "example_values",
)

TEXT_NAME_RE = re.compile(r"(?:Date|Description|Policy|Name)$", re.I)
NUMERIC_NAME_RE = re.compile(
    r"(?:Amount|Value|Number|Count|Percentage|Percent|Rate|Ratio|Balance|Assets|"
    r"Liabilities|Equity|Revenue|Profit|Loss|Costs?|Expenses?|Income|Turnover|"
    r"Capital|Cash|Creditors|Debtors|Employees)(?:DuringPeriod|AtPeriodEnd)?$",
    re.I,
)
CURRENCY_RE = re.compile(r"[A-Z]{3}")
TEXT_PREFIX_RE = re.compile(r"(?:Description|Policy|Name)", re.I)
IDENTIFIER_NAME_RE = re.compile(
    r"(?:Registered|Registration|Company|Reference|Identifier)Number$", re.I
)


@dataclass(frozen=True)
class ConceptInventoryRow:
    concept: str
    observations: int
    companies: int
    kind: str
    units: tuple[str, ...]
    context_kind: str
    pct_numeric_null: float
    example_values: tuple[str, ...]

    def as_csv_row(self) -> dict[str, object]:
        return {
            "concept": self.concept,
            "observations": self.observations,
            "companies": self.companies,
            "kind": self.kind,
            "units": "; ".join(self.units),
            "context_kind": self.context_kind,
            "pct_numeric_null": f"{self.pct_numeric_null:.2f}",
            "example_values": json.dumps(
                self.example_values, ensure_ascii=False, separators=(",", ":")
            ),
        }


@dataclass(frozen=True)
class ConceptInventoryAudit:
    non_numeric_coercions: tuple[tuple[str, int], ...]
    numeric_unit_gaps: tuple[tuple[str, int], ...]
    mixed_kinds: tuple[str, ...]
    incompatible_units: tuple[tuple[str, tuple[str, ...]], ...]
    mixed_contexts: tuple[str, ...]
    name_kind_mismatches: tuple[tuple[str, str], ...]

    @property
    def non_numeric_coercion_rows(self) -> int:
        return sum(count for _concept, count in self.non_numeric_coercions)

    @property
    def numeric_unit_gap_rows(self) -> int:
        return sum(count for _concept, count in self.numeric_unit_gaps)


@dataclass(frozen=True)
class ConceptInventory:
    rows: tuple[ConceptInventoryRow, ...]
    audit: ConceptInventoryAudit
    archive_names: tuple[str, ...]


def _unit_family(unit: str) -> str:
    parts = unit.split("/")
    return "/".join(
        "currency" if CURRENCY_RE.fullmatch(part.upper()) else part.lower()
        for part in parts
    )


def _example(raw: str, limit: int = 120) -> str:
    value = " ".join(raw.split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _counts_by_concept(
    connection: sqlite3.Connection, condition: str
) -> tuple[tuple[str, int], ...]:
    return tuple(
        (str(concept), int(count))
        for concept, count in connection.execute(
            "SELECT concept, COUNT(*) FROM observations WHERE "
            + condition
            + " GROUP BY concept ORDER BY COUNT(*) DESC, concept"
        )
    )


def build_concept_inventory(connection: sqlite3.Connection) -> ConceptInventory:
    """Scan stored observations without modifying or correcting any source value."""
    aggregate_rows = list(
        connection.execute(
            "SELECT concept, COUNT(*), COUNT(DISTINCT company), "
            "SUM(fact_kind = 'numeric'), SUM(fact_kind = 'non-numeric'), "
            "SUM(numeric_value IS NULL) FROM observations GROUP BY concept"
        )
    )
    units: dict[str, set[str]] = {}
    for concept, unit in connection.execute(
        "SELECT DISTINCT concept, unit FROM observations "
        "WHERE unit IS NOT NULL AND TRIM(unit) != ''"
    ):
        units.setdefault(str(concept), set()).add(str(unit))
    contexts: dict[str, set[str]] = {}
    for concept, context_kind in connection.execute(
        "SELECT DISTINCT concept, context_kind FROM observations"
    ):
        contexts.setdefault(str(concept), set()).add(str(context_kind))
    unknown_contexts = {
        kind for values in contexts.values() for kind in values if kind not in {"instant", "duration"}
    }
    if unknown_contexts:
        kinds = ", ".join(sorted(unknown_contexts))
        raise RuntimeError(
            f"inventory requires instant/duration context metadata; re-extract rows with: {kinds}"
        )

    examples: dict[str, list[str]] = {}
    seen_examples: dict[str, set[str]] = {}
    for concept, raw_value in connection.execute(
        "SELECT concept, raw_value FROM observations ORDER BY concept, source_year, "
        "source_month, source_archive, source_member, fact_sequence"
    ):
        concept = str(concept)
        values = examples.setdefault(concept, [])
        if len(values) >= 3:
            continue
        value = _example(str(raw_value))
        seen = seen_examples.setdefault(concept, set())
        if value not in seen:
            seen.add(value)
            values.append(value)

    rows: list[ConceptInventoryRow] = []
    numeric_counts: dict[str, int] = {}
    non_numeric_counts: dict[str, int] = {}
    for concept, observations, companies, numeric, non_numeric, numeric_null in aggregate_rows:
        concept = str(concept)
        observations = int(observations)
        numeric = int(numeric)
        non_numeric = int(non_numeric)
        numeric_counts[concept] = numeric
        non_numeric_counts[concept] = non_numeric
        kind = "mixed" if numeric and non_numeric else "numeric" if numeric else "non_numeric"
        context_values = contexts.get(concept, set())
        context_kind = (
            "mixed" if len(context_values) > 1 else next(iter(context_values), "unknown")
        )
        rows.append(
            ConceptInventoryRow(
                concept=concept,
                observations=observations,
                companies=int(companies),
                kind=kind,
                units=tuple(sorted(units.get(concept, set()))),
                context_kind=context_kind,
                pct_numeric_null=100 * int(numeric_null) / observations,
                example_values=tuple(examples.get(concept, [])),
            )
        )
    rows.sort(key=lambda row: (-row.observations, row.concept))

    mixed_kinds = tuple(row.concept for row in rows if row.kind == "mixed")
    incompatible_units = tuple(
        (row.concept, row.units)
        for row in rows
        if len({_unit_family(unit) for unit in row.units}) > 1
    )
    mixed_contexts = tuple(row.concept for row in rows if row.context_kind == "mixed")
    name_kind_mismatches = []
    for row in rows:
        if TEXT_NAME_RE.search(row.concept) and numeric_counts[row.concept]:
            name_kind_mismatches.append((row.concept, "text-like name has numeric facts"))
        numeric_like = (
            NUMERIC_NAME_RE.search(row.concept)
            and not TEXT_PREFIX_RE.match(row.concept)
            and not IDENTIFIER_NAME_RE.search(row.concept)
        )
        if numeric_like and non_numeric_counts[row.concept]:
            name_kind_mismatches.append((row.concept, "numeric-like name has non-numeric facts"))

    audit = ConceptInventoryAudit(
        non_numeric_coercions=_counts_by_concept(
            connection, "fact_kind = 'non-numeric' AND numeric_value IS NOT NULL"
        ),
        numeric_unit_gaps=_counts_by_concept(
            connection,
            "fact_kind = 'numeric' AND (unit IS NULL OR TRIM(unit) = '')",
        ),
        mixed_kinds=mixed_kinds,
        incompatible_units=incompatible_units,
        mixed_contexts=mixed_contexts,
        name_kind_mismatches=tuple(name_kind_mismatches),
    )
    archive_names = tuple(
        str(row[0])
        for row in connection.execute(
            "SELECT source_archive FROM observations GROUP BY source_archive "
            "ORDER BY MIN(source_year), MIN(source_month), source_archive"
        )
    )
    return ConceptInventory(tuple(rows), audit, archive_names)


def write_inventory_csv(inventory: ConceptInventory, output: str | Path) -> Path:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INVENTORY_COLUMNS)
        writer.writeheader()
        writer.writerows(row.as_csv_row() for row in inventory.rows)
    return destination


def _count_table(items: tuple[tuple[str, int], ...]) -> list[str]:
    if not items:
        return ["None found."]
    lines = ["| Concept | Rows |", "|---|---:|"]
    lines.extend(f"| `{concept}` | {count:,} |" for concept, count in items)
    return lines


def _concept_list(concepts: tuple[str, ...]) -> list[str]:
    if not concepts:
        return ["None found."]
    return [", ".join(f"`{concept}`" for concept in concepts)]


def render_inventory_report(inventory: ConceptInventory) -> str:
    """Render the audit and inventory anomaly surface without selecting corrections."""
    audit = inventory.audit
    total_observations = sum(row.observations for row in inventory.rows)
    lines = [
        "# Accounts concept inventory",
        "",
        "This is the Stage 1 data dictionary generated from the configured SQLite store. "
        "It reports source facts as read and does not correct or curate stored values.",
        "",
        f"- Archives represented: {len(inventory.archive_names):,}",
        f"- Source manifests: "
        f"{', '.join(f'`{name}`' for name in inventory.archive_names) or 'none'}",
        f"- Concepts: {len(inventory.rows):,}",
        f"- Observations: {total_observations:,}",
        "",
        "Only the nine core concepts are validated for fill-rate and reconciliation. All "
        "other concepts are captured but unvalidated; rare concepts should not be trusted "
        "without checking this inventory and the source filing.",
        "",
        "## Read-correctness audit",
        "",
        f"- Non-numeric facts with non-null `numeric_value`: "
        f"**{audit.non_numeric_coercion_rows:,}**",
        f"- Numeric facts with a missing or unresolved `unit`: "
        f"**{audit.numeric_unit_gap_rows:,}**",
        "",
        "### Non-numeric coercions by concept",
        "",
        *_count_table(audit.non_numeric_coercions),
        "",
        "### Numeric unit gaps by concept",
        "",
        *_count_table(audit.numeric_unit_gaps),
        "",
        "## Anomaly flags",
        "",
        "These flags are review cues, not corrections.",
        "",
        f"### Mixed numeric/non-numeric kind ({len(audit.mixed_kinds):,})",
        "",
        *_concept_list(audit.mixed_kinds),
        "",
        f"### Multiple incompatible unit families ({len(audit.incompatible_units):,})",
        "",
    ]
    if audit.incompatible_units:
        lines.extend(["| Concept | Units |", "|---|---|"])
        lines.extend(
            f"| `{concept}` | {', '.join(f'`{unit}`' for unit in units)} |"
            for concept, units in audit.incompatible_units
        )
    else:
        lines.append("None found.")
    lines.extend(
        [
            "",
            f"### Mixed instant/duration context ({len(audit.mixed_contexts):,})",
            "",
            *_concept_list(audit.mixed_contexts),
            "",
            f"### Name-versus-kind mismatch ({len(audit.name_kind_mismatches):,})",
            "",
        ]
    )
    if audit.name_kind_mismatches:
        lines.extend(["| Concept | Reason |", "|---|---|"])
        lines.extend(
            f"| `{concept}` | {reason} |"
            for concept, reason in audit.name_kind_mismatches
        )
    else:
        lines.append("None found.")
    lines.extend(
        [
            "",
            "## CSV data dictionary",
            "",
            "`accounts-concept-inventory.csv` contains one row per concept, sorted by "
            "observation count. `example_values` is a compact JSON array of up to three "
            "distinct source-text examples; examples are whitespace-normalised and truncated "
            "to 120 characters only for display.",
            "",
        ]
    )
    return "\n".join(lines)


def write_concept_inventory(
    connection: sqlite3.Connection,
    csv_output: str | Path,
    report_output: str | Path,
) -> ConceptInventory:
    inventory = build_concept_inventory(connection)
    write_inventory_csv(inventory, csv_output)
    report = Path(report_output)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_inventory_report(inventory), encoding="utf-8")
    return inventory
