"""Apply the rule registry to derived attributes -> long-format flag table.

Excluded-status companies (dissolved etc.) and not-found numbers are reported
in their own tables, not scored: scoring a dissolved company would be
answering a question nobody asked.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .rules import REGISTRY

Attributes = dict[str, Any]


def score_company(attrs: Attributes) -> list[dict[str, Any]]:
    flags = []
    for rule in REGISTRY:
        evidence = rule.func(attrs)
        if evidence is not None:
            flags.append(
                {
                    "company_number": attrs.get("company_number"),
                    "rule_id": rule.rule_id,
                    "severity": rule.severity,
                    "evidence": evidence,
                    "observed_at": attrs.get("observed_at"),
                }
            )
    return flags


def score_all(records: list[Attributes]) -> dict[str, list[dict[str, Any]]]:
    """Partition into scored flags / exclusions / not-found."""
    flags: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    not_found: list[dict[str, Any]] = []
    for attrs in records:
        if not attrs.get("found"):
            not_found.append(
                {
                    "company_number": attrs.get("company_number"),
                    "observed_at": attrs.get("observed_at"),
                }
            )
            continue
        if attrs.get("excluded_status"):
            excluded.append(
                {
                    "company_number": attrs.get("company_number"),
                    "company_status": attrs.get("company_status"),
                    "observed_at": attrs.get("observed_at"),
                }
            )
            continue
        flags.extend(score_company(attrs))
    return {"flags": flags, "excluded": excluded, "not_found": not_found}


def write_csv(rows: list[dict[str, Any]], path: str | Path, fieldnames: list[str] | None = None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    if fieldnames is None:
        # Union of keys, first-seen order - records may have heterogeneous keys.
        fieldnames = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarise(result: dict[str, list[dict[str, Any]]], n_input: int) -> str:
    flags = result["flags"]
    by_sev: dict[str, int] = {}
    for fl in flags:
        by_sev[fl["severity"]] = by_sev.get(fl["severity"], 0) + 1
    companies_flagged = len({f["company_number"] for f in flags if f["severity"] != "info"})
    return "\n".join(
        [
            f"companies in: {n_input}",
            f"excluded (dissolved/closed): {len(result['excluded'])}",
            f"not found: {len(result['not_found'])}",
            f"flags: {len(flags)} "
            f"(high: {by_sev.get('high', 0)}, medium: {by_sev.get('medium', 0)}, "
            f"low: {by_sev.get('low', 0)}, info: {by_sev.get('info', 0)})",
            f"companies with >=1 non-info flag: {companies_flagged}",
        ]
    )
