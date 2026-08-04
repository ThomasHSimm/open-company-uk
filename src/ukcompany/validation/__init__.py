"""Cache-only agreement evaluation against external insolvency labels.

This package is an evaluation tool.  Production scoring must never import it.
"""

from .evaluate import EvaluationResult, evaluate
from .labels import Label, LabelSet, load_labels
from .report import render_report, write_report

__all__ = [
    "EvaluationResult",
    "Label",
    "LabelSet",
    "evaluate",
    "load_labels",
    "render_report",
    "write_report",
]
