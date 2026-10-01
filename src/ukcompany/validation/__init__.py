"""Cache-only agreement evaluation against external insolvency labels.

This package is an evaluation tool.  Production scoring must never import it.
"""

from .control import (
    ControlMember,
    ControlPlan,
    StratifiedTargets,
    draw_control,
    read_control_csv,
    snapshot_sic_section,
    stratify_targets,
    write_control_csv,
)
from .evaluate import EvaluationResult, evaluate
from .labels import Label, LabelSet, load_labels, sic_section_from_code
from .report import render_report, write_report
from .sample import PositivesSample, sample_positives, write_positives_csv

__all__ = [
    "ControlMember",
    "ControlPlan",
    "EvaluationResult",
    "Label",
    "LabelSet",
    "PositivesSample",
    "StratifiedTargets",
    "draw_control",
    "evaluate",
    "load_labels",
    "read_control_csv",
    "render_report",
    "sample_positives",
    "sic_section_from_code",
    "snapshot_sic_section",
    "stratify_targets",
    "write_control_csv",
    "write_positives_csv",
    "write_report",
]
