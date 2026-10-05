"""Leak check for committed PSC aggregates — site assets and walkthrough notebook outputs.

Governed PSC outputs that get committed (the site's `docs/site/datasets/psc-assets/` CSVs/JSON and
the executed `notebooks/*.ipynb`) must be aggregates only. This gate scans their text for:

  * **company numbers** in the leading-zero form `0#######` or the prefixed form `AA######`
    (counts never start with a zero and never carry a letter prefix, so these patterns only appear
    if a real company number leaked). Bare 8-digit numbers with no leading zero are *not* flagged:
    they are indistinguishable from large counts, and the aggregates never list companies anyway.
  * an **HMAC `person_key`** (a 64-char hex string);
  * raw **personal fields** (nationality, date of birth, …) appearing as data;
  * **un-suppressed sub-10 counts** in CSV count columns (they must read `<10`).

stdlib only, so it runs in CI with no extra dependencies. Exit status is non-zero on any finding.

    python scripts/psc_leak_check.py                      # defaults: psc-assets + notebooks
    python scripts/psc_leak_check.py path1 path2 ...      # explicit files/globs
"""

from __future__ import annotations

import csv
import glob
import json
import re
import sys
from pathlib import Path

COMPANY = re.compile(r"\b(?:0\d{7}|[A-Z]{2}\d{6})\b")
HEX64 = re.compile(r"\b[0-9a-f]{64}\b")
PII = re.compile(r"\b(nationality|date_of_birth|dob_year|dob_month|residential_address)\b", re.I)

# JSON keys whose value is legitimate provenance (a script/commit hash), never personal data, so
# their 64-hex values are not HMAC person_keys.
PROVENANCE_KEYS = {"script_sha256", "sha256", "generated_against_commit", "commit",
                   "generated_by_script"}

DEFAULT_TARGETS = ("docs/site/datasets/psc-assets/*.csv",
                   "docs/site/datasets/psc-assets/*.json",
                   "notebooks/*.ipynb")


def _scan_text(text: str) -> list[tuple[str, str]]:
    out = []
    for m in COMPANY.finditer(text):
        out.append(("company_number", m.group(0)))
    for m in HEX64.finditer(text):
        out.append(("hmac_person_key", m.group(0)[:12] + "…"))
    for m in PII.finditer(text):
        out.append(("personal_field", m.group(0)))
    return out


def _notebook_output_text(path: Path) -> str:
    nb = json.loads(path.read_text(encoding="utf-8"))
    chunks = []
    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        for o in cell.get("outputs", []):
            t = o.get("text")
            if t is None:
                t = (o.get("data", {}) or {}).get("text/plain", "")
            chunks.append("".join(t) if isinstance(t, list) else (t or ""))
    return "\n".join(chunks)


def _scan_json_values(obj, findings: list[tuple[str, str]]) -> None:
    """Scan JSON string values, skipping provenance-key values (script/commit hashes). Numeric
    values (counts) are not scanned at all, so large counts never read as company numbers."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in PROVENANCE_KEYS:
                continue
            _scan_json_values(v, findings)
    elif isinstance(obj, list):
        for v in obj:
            _scan_json_values(v, findings)
    elif isinstance(obj, str):
        findings.extend(_scan_text(obj))


def _csv_unsuppressed(path: Path) -> list[str]:
    """Rows whose final (count) cell is a bare 1-9 integer (should be '<10')."""
    bad = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row:
                continue
            last = row[-1].strip().replace(",", "")
            if last.isdigit() and 0 < int(last) < 10:
                bad.append(",".join(row))
    return bad


def main(argv: list[str]) -> int:
    targets = argv or list(DEFAULT_TARGETS)
    paths = sorted({Path(p) for pat in targets for p in glob.glob(pat)})
    findings: list[str] = []
    checked = 0
    for path in paths:
        checked += 1
        if path.suffix == ".json":
            local: list[tuple[str, str]] = []
            _scan_json_values(json.loads(path.read_text(encoding="utf-8")), local)
            for kind, tok in local:
                findings.append(f"{path}: {kind}: {tok!r}")
            continue
        text = _notebook_output_text(path) if path.suffix == ".ipynb" else \
            path.read_text(encoding="utf-8", errors="replace")
        for kind, tok in _scan_text(text):
            findings.append(f"{path}: {kind}: {tok!r}")
        if path.suffix == ".csv":
            for row in _csv_unsuppressed(path):
                findings.append(f"{path}: un-suppressed sub-10 count in row: {row!r}")

    print(f"leak check: scanned {checked} file(s)")
    if not findings:
        print("RESULT: PASS — aggregates only, no leak")
        return 0
    print("RESULT: FAIL")
    for f in findings:
        print("  ", f)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
