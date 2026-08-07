"""Markdown separation report for the insolvency agreement evaluation."""

from __future__ import annotations

from pathlib import Path

from .evaluate import EvaluationResult
from .labels import LabelSet


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


AGE_BAND_ORDER = ("<2y", "2-5y", "5-10y", "10y+", "UNKNOWN")


def _control_section(result: EvaluationResult) -> list[str]:
    lines = ["", "## Stratified control sample", ""]
    plan = result.control_plan
    if not result.control_total:
        lines.append("No control sample was supplied.")
        return lines

    frame = plan.frame_description if plan and plan.frame_description else "supplied list"
    lines += [
        f"Sampling frame: **{frame}**.",
        "",
        "**Positive-unlabelled caveat.** No negative labels exist. The Insolvency "
        "Service publication lists only adverse cases, so the control is an "
        "*assumed-not-labelled-negative* cohort, not confirmed non-distressed. The "
        "figure below is a flag-RATE conditional on this frame; it is NOT precision "
        "and must not be read as a false-positive rate against ground truth.",
        "",
    ]

    rate = len(result.control_high_severity) / result.control_total
    lines.append(
        f"{len(result.control_high_severity)} of {result.control_total} controls "
        f"({_percent(rate)}) fired at least one high-severity flag."
    )

    if plan and (plan.target_counts or plan.achieved_counts):
        strata = sorted(set(plan.target_counts) | set(plan.achieved_counts))
        lines += [
            "",
            "### Target vs achieved strata (SIC section x age band)",
            "",
            "| Section | Age band | Target | Achieved |",
            "|---|---|---:|---:|",
        ]
        for stratum in strata:
            section, _, band = stratum.partition("|")
            lines.append(
                f"| {section} | {band} | {plan.target_counts.get(stratum, 0)} | "
                f"{plan.achieved_counts.get(stratum, 0)} |"
            )

    lines += [
        "",
        "### Control flag-rate by age band (age as covariate)",
        "",
        "| Age band | Controls | High-severity | Flag-rate |",
        "|---|---:|---:|---:|",
    ]
    bands = [b for b in AGE_BAND_ORDER if b in result.control_by_band]
    bands += sorted(set(result.control_by_band) - set(AGE_BAND_ORDER))
    for band in bands:
        total, high = result.control_by_band[band]
        band_rate = high / total if total else None
        lines.append(f"| {band} | {total} | {high} | {_percent(band_rate)} |")
    return lines


def render_report(result: EvaluationResult, labels: LabelSet) -> str:
    counts = result.counts()
    lines = [
        "# Insolvency indicator separation report",
        "",
        "## Interpretation",
        "",
        "This report measures **agreement between two datasets, not ground truth about reality**. "
        "The Insolvency Service states that its data is provided for statistical purposes only, "
        "cannot be guaranteed free from error, and should not be used to determine whether a "
        "particular company is insolvent. Solvent liquidations are absent from these labels, so "
        "this report evaluates adverse classification only.",
        "",
        "The headline measure is **conditional recall among still-assessable companies**: "
        "`flagged_adverse / (flagged_adverse + missed_genuine)`. Cached 404/purged companies, "
        "companies whose current status has moved back to normal, and records never fetched are "
        "excluded from its denominator. The raw counts below make those exclusions explicit.",
        "",
        "## Recall by case type",
        "",
        "| Case type | Flagged adverse | Genuine miss | Assessable | Conditional recall |",
        "|---|---:|---:|---:|---:|",
    ]
    for case_type in result.case_types():
        row = result.counts(case_type)
        assessable = row["flagged_adverse"] + row["missed_genuine"]
        lines.append(
            f"| {case_type} | {row['flagged_adverse']} | {row['missed_genuine']} | "
            f"{assessable} | {_percent(result.recall(case_type))} |"
        )
    assessable = counts["flagged_adverse"] + counts["missed_genuine"]
    lines += [
        f"| **Overall** | **{counts['flagged_adverse']}** | **{counts['missed_genuine']}** | "
        f"**{assessable}** | **{_percent(result.recall())}** |",
        "",
        "## Full positive-outcome breakdown",
        "",
        "| Outcome | Count | Included in recall denominator? |",
        "|---|---:|---|",
        f"| Flagged adverse | {counts['flagged_adverse']} | Yes |",
        f"| Genuine miss | {counts['missed_genuine']} | Yes |",
        f"| Cached 404 / purged | {counts['missed_404']} | No |",
        f"| Status moved / currently normal | {counts['missed_status_moved']} | No |",
        f"| Not fetched | {counts['not_fetched']} | No |",
        "",
        "### Genuine misses to investigate",
        "",
    ]
    genuine = [row for row in result.outcomes if row.outcome == "missed_genuine"]
    lines += [f"- `{row.company_number}` — {row.raw_case_type}" for row in genuine] or ["None."]
    lines += [
        "",
        "## SOLVENT_WINDING_UP classification errors",
        "",
        "**ERROR: any entry here is an adverse-labelled positive classified as a solvent "
        "winding-up and must be investigated.**",
        "",
    ]
    lines += [
        f"- `{row.company_number}` — label: {row.raw_case_type}"
        for row in result.solvent_winding_up_errors
    ] or ["Zero errors."]
    lines += _control_section(result)
    lines += [
        "",
        "## Label loading",
        "",
        f"Input rows: {labels.input_rows}; retained unique labels: {len(labels.labels)}; "
        f"bulk rows dropped: {labels.dropped_bulk}; Administration-to-CVL rows dropped: "
        f"{labels.dropped_administration_to_cvl}; unusable company numbers: "
        f"{len(labels.unusable)}; field-shifted rows quarantined: {labels.unusable_shifted}; "
        f"duplicate rows: {labels.duplicate_rows}.",
        "",
        "## Temporal caveat",
        "",
        "The publication covers insolvencies registered from 2012 through April 2024, while "
        "the Companies House cache reflects a later/current API state. Older positives may now "
        "be dissolved and purged (404), or may have moved to a normal status. Those are "
        "data-availability and timing facts and are reported separately from genuine misses.",
        "",
    ]
    return "\n".join(lines)


def write_report(result: EvaluationResult, labels: LabelSet, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_report(result, labels), encoding="utf-8")
    return output
