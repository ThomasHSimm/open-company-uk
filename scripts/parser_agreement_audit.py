"""Regex-vs-lxml parser-agreement audit for early-year accounts filings.

The production extractor (src/ukcompany/accounts/core.py) locates inline-XBRL facts with a
regex (`IX_FACT_RE`) for speed across hundreds of millions of filings. That regex was tuned
and validated against 2019-2025 markup only. This script independently re-parses a sample
of filings with lxml's real XML parser and checks that the two approaches find the same set
of (concept, contextRef, raw text) fact tuples — the risk this guards against is the fast
regex silently under- or over-matching on older filing-software markup quirks it was never
tested against. The extraction invariant closing (facts_seen == accounted) only proves nothing
was lost *after* a fact was found; it says nothing about facts the regex never found at all,
which is exactly what this script checks.

Usage:
    python scripts/parser_agreement_audit.py <archive.zip> [<archive.zip> ...] \
        --sample-size 200 --seed 1
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ukcompany.accounts.core import (  # noqa: E402
    IX_FACT_RE,
    local_name,
    parse_attrs,
    text_content,
)


@dataclass(frozen=True)
class FilingDiff:
    member: str
    regex_facts: int
    lxml_facts: int
    regex_only: tuple[tuple[str, str, str], ...]
    lxml_only: tuple[tuple[str, str, str], ...]
    parse_error: str | None = None

    @property
    def agrees(self) -> bool:
        return not self.regex_only and not self.lxml_only and self.parse_error is None


def regex_fact_set(data: bytes) -> set[tuple[str, str, str]]:
    """Mirror core.py's own candidate-detection step: every ix:nonFraction/nonNumeric the
    production regex finds, identified the same way core.py identifies a fact."""
    facts = set()
    for _raw_tag, raw_attrs, body in IX_FACT_RE.findall(data):
        attrs = parse_attrs(raw_attrs)
        concept = local_name(attrs.get("name", ""))
        if not concept:
            continue
        context_ref = attrs.get("contextref", "")
        raw_value = text_content(body)
        facts.add((concept, context_ref, raw_value))
    return facts


def lxml_fact_set(data: bytes) -> tuple[set[tuple[str, str, str]], str | None]:
    """Independent extraction via lxml's real XML parser, not the production regex."""
    from lxml import etree

    parser = etree.XMLParser(recover=True, huge_tree=True)
    try:
        tree = etree.fromstring(data, parser=parser)
    except etree.XMLSyntaxError as exc:
        return set(), str(exc)
    if tree is None:
        return set(), "lxml returned no tree"
    facts = set()
    for element in tree.iter():
        if not isinstance(element.tag, str):
            continue
        local = element.tag.rsplit("}", 1)[-1]
        if local.lower() not in ("nonfraction", "nonnumeric"):
            continue
        attrs = {key.rsplit("}", 1)[-1].lower(): value for key, value in element.attrib.items()}
        concept = local_name(attrs.get("name", ""))
        if not concept:
            continue
        context_ref = attrs.get("contextref", "")
        # Match core.py's text_content() exactly (strip tags, unescape entities, normalise
        # nbsp, strip ends) — do NOT collapse internal whitespace, or every filing with
        # multi-line narrative text becomes a false-positive "disagreement".
        raw_value = "".join(element.itertext()).replace(" ", " ").strip()
        facts.add((concept, context_ref, raw_value))
    return facts, None


MEMBER_RE = re.compile(r"^Prod\d+_\d{4}_[^_]+_\d{8}\.(html|htm)$", re.I)


def sample_members(paths: list[Path], sample_size: int, seed: int) -> list[tuple[Path, str]]:
    candidates: list[tuple[Path, str]] = []
    for path in paths:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if not info.is_dir() and MEMBER_RE.match(Path(info.filename).name):
                    candidates.append((path, info.filename))
    rng = random.Random(seed)
    if len(candidates) > sample_size:
        candidates = rng.sample(candidates, sample_size)
    return candidates


def audit(paths: list[Path], sample_size: int, seed: int) -> list[FilingDiff]:
    members = sample_members(paths, sample_size, seed)
    results = []
    open_zips: dict[Path, zipfile.ZipFile] = {}
    try:
        for path, member in members:
            archive = open_zips.setdefault(path, zipfile.ZipFile(path))
            data = archive.read(member)
            regex_facts = regex_fact_set(data)
            lxml_facts, parse_error = lxml_fact_set(data)
            results.append(
                FilingDiff(
                    member=f"{path.name}:{member}",
                    regex_facts=len(regex_facts),
                    lxml_facts=len(lxml_facts),
                    regex_only=tuple(sorted(regex_facts - lxml_facts))[:5],
                    lxml_only=tuple(sorted(lxml_facts - regex_facts))[:5],
                    parse_error=parse_error,
                )
            )
    finally:
        for archive in open_zips.values():
            archive.close()
    return results


def render_report(results: list[FilingDiff], paths: list[Path]) -> str:
    total = len(results)
    agree = sum(result.agrees for result in results)
    parse_errors = sum(result.parse_error is not None for result in results)
    disagreements = [result for result in results if not result.agrees]
    agree_pct = f"{100 * agree / total:.1f}%" if total else "n/a"
    lines = [
        "# Regex-vs-lxml parser-agreement audit",
        "",
        f"Archives: {', '.join(path.name for path in paths)}",
        f"Filings sampled: {total:,}",
        f"Exact agreement (same fact set): {agree:,} ({agree_pct})",
        f"lxml parse errors: {parse_errors:,}",
        "",
        "## Disagreements",
        "",
    ]
    if not disagreements:
        lines.append("None found.")
    else:
        lines.append(
            "| Filing | Regex facts | lxml facts | Regex-only (sample) | "
            "lxml-only (sample) | Parse error |"
        )
        lines.append("|---|---:|---:|---|---|---|")
        for result in disagreements[:50]:
            lines.append(
                f"| `{result.member}` | {result.regex_facts} | {result.lxml_facts} | "
                f"{json.dumps(result.regex_only)} | {json.dumps(result.lxml_only)} | "
                f"{result.parse_error or ''} |"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--sample-size", type=int, default=200)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    results = audit(args.archives, args.sample_size, args.seed)
    report = render_report(results, args.archives)
    print(report)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report, encoding="utf-8")
    disagreements = sum(not result.agrees for result in results)
    return 1 if disagreements else 0


if __name__ == "__main__":
    sys.exit(main())
