#!/usr/bin/env python3
"""Reconnaissance over Companies House monthly accounts ZIP archives.

This script deliberately lives outside the package. It reads sampled filings directly
from ZIP members in memory and writes an aggregate Markdown report; it never extracts
or persists filing data.
"""

from __future__ import annotations

import argparse
import math
import re
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

try:
    from lxml import etree
except ImportError:  # The byte-tolerant extraction below has no hard dependency.
    etree = None  # type: ignore[assignment]

ARCHIVE_RE = re.compile(r"^\s*Accounts_Monthly_Data-([A-Za-z]+)(\d{4})\.zip\s*$", re.I)
MEMBER_RE = re.compile(
    r"^Prod\d+_\d{4}_([^_]+)_(\d{8})\.(html|xml)$",
    re.I,
)
DEFAULT_POINTS = {(2019, "january"), (2020, "january"), (2021, "january"), (2022, "january"), (2025, "august")}
TARGET_CONCEPTS = (
    "CashBankOnHand",
    "CurrentAssets",
    "Creditors",
    "NetCurrentAssetsLiabilities",
    "Equity",
    "TotalAssetsLessCurrentLiabilities",
    "Debtors",
    "PropertyPlantEquipment",
    "AverageNumberEmployeesDuringPeriod",
    "UKCompaniesHouseRegisteredNumber",
)
CAPTURE_CONCEPTS = {"CashBankOnHand", "Equity"}
ATTR_RE = re.compile(rb"([:\w.-]+)\s*=\s*(['\"])(.*?)\2", re.S)
TAG_RE = re.compile(rb"<\s*([\w.-]+):([\w.-]+)\b([^>]*)>(.*?)</\s*\1:\2\s*>", re.I | re.S)
IX_FACT_RE = re.compile(rb"<\s*ix:(?:nonFraction|nonNumeric)\b([^>]*)>(.*?)</\s*ix:(?:nonFraction|nonNumeric)\s*>", re.I | re.S)
XMLNS_RE = re.compile(rb"\bxmlns(?::([\w.-]+))?\s*=\s*(['\"])(.*?)\2", re.I | re.S)
PERIOD_RE = re.compile(rb"<\s*(?:[\w.-]+:)?(instant|endDate)\b[^>]*>(.*?)</", re.I | re.S)
TAG_STRIP_RE = re.compile(rb"<[^>]+>")


@dataclass(frozen=True)
class ValueExample:
    raw: str
    scale: str
    decimals: str
    unit: str


@dataclass
class FilingResult:
    member: str
    kind: str
    company: str | None = None
    filing_date: str | None = None
    concepts: set[str] = field(default_factory=set)
    namespaces: set[str] = field(default_factory=set)
    values: dict[str, list[ValueExample]] = field(default_factory=lambda: defaultdict(list))
    tagged_companies: set[str] = field(default_factory=set)
    period_ends: set[str] = field(default_factory=set)
    parse_error: str | None = None


@dataclass
class ArchiveResult:
    year: int
    month: str
    path: Path
    total_members: int
    sampled: list[FilingResult]
    filename_exceptions: list[str]


def local_name(name: str) -> str:
    """Return the namespace-independent part of an XML/XBRL name."""
    return name.rsplit(":", 1)[-1].rsplit("}", 1)[-1]


def parse_member_filename(member: str) -> tuple[str, str] | None:
    """Extract company number and filing date from a filing member basename."""
    match = MEMBER_RE.fullmatch(Path(member.strip()).name)
    return (match.group(1), match.group(2)) if match else None


def _attrs(raw: bytes) -> dict[str, str]:
    return {
        key.decode("utf-8", "replace").lower(): value.decode("utf-8", "replace").strip()
        for key, _, value in ATTR_RE.findall(raw)
    }


def _text(raw: bytes) -> str:
    return TAG_STRIP_RE.sub(b"", raw).decode("utf-8", "replace").strip()


def _normalise_company(value: str) -> str:
    return re.sub(r"\s+", "", value).upper().lstrip("0") or "0"


def _parse_document(data: bytes, kind: str) -> str | None:
    if not data.strip():
        return "empty document"
    if etree is None:
        # Extraction is regex-based by design. This fallback only distinguishes
        # recognisable markup from unreadable/empty member content.
        return None if re.search(rb"<\s*[!?/]?[\w:.-]+(?:\s|>)", data) else "no markup root detected"
    try:
        if kind == "ixbrl-html":
            root = etree.fromstring(data, etree.HTMLParser(recover=True))
        else:
            root = etree.fromstring(data, etree.XMLParser(recover=True, huge_tree=True))
    except (etree.XMLSyntaxError, ValueError, TypeError) as exc:
        return f"{type(exc).__name__}: {exc}"
    return None if root is not None else "parser returned no document root"


def detect_facts(data: bytes, kind: str) -> tuple[set[str], dict[str, list[ValueExample]], set[str]]:
    """Detect target facts with byte-tolerant patterns for iXBRL and XBRL."""
    concepts: set[str] = set()
    values: dict[str, list[ValueExample]] = defaultdict(list)
    companies: set[str] = set()
    matches: Iterable[tuple[bytes, bytes]]
    if kind == "ixbrl-html":
        matches = ((attrs, body) for attrs, body in IX_FACT_RE.findall(data))
        for raw_attrs, body in matches:
            attrs = _attrs(raw_attrs)
            concept = local_name(attrs.get("name", ""))
            if concept not in TARGET_CONCEPTS:
                continue
            raw = _text(body)
            concepts.add(concept)
            if concept in CAPTURE_CONCEPTS:
                values[concept].append(ValueExample(raw, attrs.get("scale", ""), attrs.get("decimals", ""), attrs.get("unitref", "")))
            if concept == "UKCompaniesHouseRegisteredNumber" and raw:
                companies.add(raw)
    else:
        for _prefix, raw_name, raw_attrs, body in TAG_RE.findall(data):
            concept = raw_name.decode("ascii", "ignore")
            if concept not in TARGET_CONCEPTS:
                continue
            attrs = _attrs(raw_attrs)
            raw = _text(body)
            concepts.add(concept)
            if concept in CAPTURE_CONCEPTS:
                values[concept].append(ValueExample(raw, attrs.get("scale", ""), attrs.get("decimals", ""), attrs.get("unitref", "")))
            if concept == "UKCompaniesHouseRegisteredNumber" and raw:
                companies.add(raw)
    return concepts, values, companies


def parse_filing(member: str, data: bytes) -> FilingResult:
    suffix = Path(member).suffix.lower()
    kind = "ixbrl-html" if suffix in {".html", ".htm"} else "xbrl-xml" if suffix == ".xml" else "other"
    result = FilingResult(member=member, kind=kind)
    filename = parse_member_filename(member)
    if filename:
        result.company, result.filing_date = filename
    if kind == "other":
        return result
    result.parse_error = _parse_document(data, kind)
    result.namespaces = {
        uri.decode("utf-8", "replace").strip()
        for _prefix, _quote, uri in XMLNS_RE.findall(data)
        if uri.strip()
    }
    result.period_ends = {_text(value) for _tag, value in PERIOD_RE.findall(data) if _text(value)}
    concepts, values, companies = detect_facts(data, kind)
    result.concepts = concepts
    result.values = values
    result.tagged_companies = companies
    return result


def spread_sample(items: list[str], size: int) -> list[str]:
    """Choose evenly spaced members, including both ends, without duplicates."""
    if size <= 0:
        raise ValueError("sample size must be positive")
    if len(items) <= size:
        return items
    indexes = [math.floor(index * len(items) / size) for index in range(size)]
    return [items[index] for index in indexes]


def inspect_archive(path: Path, year: int, month: str, sample_size: int) -> ArchiveResult:
    with zipfile.ZipFile(path) as archive:
        members = [info.filename for info in archive.infolist() if not info.is_dir()]
        filing_members = [name for name in members if Path(name).suffix.lower() in {".html", ".htm", ".xml"}]
        exceptions = [name for name in filing_members if parse_member_filename(name) is None]
        sampled_names = spread_sample(members, sample_size)
        sampled = []
        for member in sampled_names:
            try:
                sampled.append(parse_filing(member, archive.read(member)))
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                sampled.append(FilingResult(member, "other", parse_error=f"{type(exc).__name__}: {exc}"))
    return ArchiveResult(year, month, path, len(members), sampled, exceptions)


def discover_archives(downloads: Path) -> list[tuple[Path, int, str]]:
    found = []
    for path in downloads.glob("*Accounts_Monthly_Data-*.zip*"):
        match = ARCHIVE_RE.fullmatch(path.name)
        if not match:
            continue
        month, year_text = match.groups()
        year = int(year_text)
        if (year, month.lower()) in DEFAULT_POINTS:
            found.append((path, year, month.title()))
    return sorted(found, key=lambda item: item[1])


def archive_arg(path_text: str) -> tuple[Path, int, str]:
    path = Path(path_text).expanduser()
    match = ARCHIVE_RE.fullmatch(path.name)
    if not match:
        raise ValueError(f"archive filename does not match expected pattern: {path.name!r}")
    month, year = match.groups()
    return path, int(year), month.title()


def percentage(count: int, denominator: int) -> str:
    return f"{100 * count / denominator:.1f}%" if denominator else "n/a"


def company_mismatches(result: ArchiveResult) -> list[str]:
    mismatches = []
    for filing in result.sampled:
        if not filing.company or not filing.tagged_companies:
            continue
        expected = _normalise_company(filing.company)
        observed = {_normalise_company(value) for value in filing.tagged_companies}
        if expected not in observed:
            mismatches.append(f"`{filing.member}`: filename `{filing.company}`, tag(s) {', '.join(sorted(filing.tagged_companies))}")
    return mismatches


def taxonomy_uris(result: ArchiveResult) -> Counter[str]:
    counter: Counter[str] = Counter()
    for filing in result.sampled:
        counter.update(uri for uri in filing.namespaces if "frc" in uri.lower())
    return counter


def render_report(results: list[ArchiveResult], sample_size: int) -> str:
    years = [str(result.year) for result in results]
    lines = [
        "# Accounts monthly data reconnaissance",
        "",
        f"Generated from an evenly spread sample of up to {sample_size} ZIP members per archive. Filings were read in memory; no archive was extracted. Percentages use all sampled members as the denominator.",
        "",
        "## Sample and format split",
        "",
        "| Year (month) | ZIP members | Sampled | iXBRL HTML | XBRL XML | Other | Unparseable |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        counts = Counter(item.kind for item in result.sampled)
        bad = sum(item.parse_error is not None for item in result.sampled)
        n = len(result.sampled)
        lines.append(
            f"| {result.year} ({result.month}) | {result.total_members} | {n} | {counts['ixbrl-html']} ({percentage(counts['ixbrl-html'], n)}) | {counts['xbrl-xml']} ({percentage(counts['xbrl-xml'], n)}) | {counts['other']} ({percentage(counts['other'], n)}) | {bad} |"
        )
    lines.extend(["", "## Concept fill-rate matrix", "", "| Concept | " + " | ".join(years) + " |", "|---|" + "---:|" * len(years)])
    for concept in TARGET_CONCEPTS:
        cells = [percentage(sum(concept in item.concepts for item in result.sampled), len(result.sampled)) for result in results]
        lines.append(f"| `{concept}` | " + " | ".join(cells) + " |")

    lines.extend(["", "## Taxonomy and namespace drift", ""])
    for result in results:
        lines.append(f"### {result.year} ({result.month})")
        lines.append("")
        uris = taxonomy_uris(result)
        if uris:
            lines.extend(f"- `{uri}` — {count} sampled filings" for uri, count in uris.most_common())
        else:
            lines.append("No namespace URI containing `frc` was detected.")
        lines.append("")

    lines.extend(["## Magnitude and formatting conventions", ""])
    for result in results:
        examples = [example for item in result.sampled for values in item.values.values() for example in values]
        scales = sorted({example.scale or "(missing)" for example in examples})
        decimals = sorted({example.decimals or "(missing)" for example in examples})
        units = Counter(example.unit or "(missing)" for example in examples)
        comma = sum("," in example.raw for example in examples)
        negative = sum(example.raw.lstrip().startswith("-") or ("(" in example.raw and ")" in example.raw) for example in examples)
        period_dates = sorted({date for item in result.sampled for date in item.period_ends})
        lines.append(f"### {result.year} ({result.month})")
        lines.append("")
        lines.append(f"Across {len(examples)} captured CashBankOnHand/Equity facts: scales {', '.join(f'`{x}`' for x in scales) or 'none'}; decimals {', '.join(f'`{x}`' for x in decimals) or 'none'}. Comma-formatted: {comma}; negative/parenthesised: {negative}. Units: " + (", ".join(f"`{unit}` ({count})" for unit, count in units.most_common()) or "none") + ".")
        for concept in sorted(CAPTURE_CONCEPTS):
            concept_examples = [
                example
                for item in result.sampled
                for example in item.values.get(concept, [])
            ][:5]
            if concept_examples:
                rendered = "; ".join(
                    f"raw `{example.raw}`, scale `{example.scale or '(missing)'}`, "
                    f"decimals `{example.decimals or '(missing)'}`, "
                    f"unit `{example.unit or '(missing)'}`"
                    for example in concept_examples
                )
                lines.append(f"Representative `{concept}` facts: {rendered}.")
        if period_dates:
            lines.append(f"Detected period-end/instant values from `{period_dates[0]}` to `{period_dates[-1]}` ({len(period_dates)} distinct values).")
        else:
            lines.append("No period-end or instant values were detected.")
        lines.append("")

    lines.extend(["## Filename and company-number checks", ""])
    for result in results:
        mismatches = company_mismatches(result)
        lines.append(f"### {result.year} ({result.month})")
        lines.append("")
        lines.append(f"Filename-pattern exceptions across all filing members: {len(result.filename_exceptions)}.")
        lines.extend(f"- `{name}`" for name in result.filename_exceptions[:50])
        if len(result.filename_exceptions) > 50:
            lines.append(f"- … {len(result.filename_exceptions) - 50} more (list capped at 50)")
        lines.append(f"Tag-vs-filename company-number mismatches in the sample: {len(mismatches)}.")
        lines.extend(f"- {item}" for item in mismatches[:50])
        if len(mismatches) > 50:
            lines.append(f"- … {len(mismatches) - 50} more (list capped at 50)")
        lines.append("")

    company_years: dict[str, set[int]] = defaultdict(set)
    for result in results:
        for item in result.sampled:
            if item.company:
                company_years[item.company].add(result.year)
    candidates = sorted((company, sorted(company_year_set)) for company, company_year_set in company_years.items() if len(company_year_set) >= 3)
    lines.extend(["## Candidate longitudinal companies", "", "Companies appearing in at least three sampled years. Sampling means omission here does not imply absence from an archive.", ""])
    if candidates:
        lines.extend(f"- `{company}` — {', '.join(map(str, company_year_set))}" for company, company_year_set in candidates)
    else:
        lines.append("None found in the sampled filings.")
    lines.append("")
    return "\n".join(lines)


def print_summary(results: list[ArchiveResult]) -> None:
    for result in results:
        counts = Counter(item.kind for item in result.sampled)
        n = len(result.sampled)
        rates = [(sum(concept in item.concepts for item in result.sampled) / n if n else 0, concept) for concept in TARGET_CONCEPTS]
        lowest = ", ".join(f"{concept} {rate:.1%}" for rate, concept in sorted(rates)[:3])
        print(f"{result.year}: n={n}; HTML={percentage(counts['ixbrl-html'], n)}, XML={percentage(counts['xbrl-xml'], n)}, other={percentage(counts['other'], n)}; lowest: {lowest}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="*", help="archive paths; defaults to the five requested samples in ~/Downloads")
    parser.add_argument("-n", "--sample-size", type=int, default=300, help="members sampled per ZIP (default: 300)")
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads", help="directory used for default discovery")
    parser.add_argument("--output", type=Path, default=Path("docs/recon-accounts.md"), help="Markdown report path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        archives = [archive_arg(value) for value in args.archives] if args.archives else discover_archives(args.downloads)
        if args.sample_size <= 0:
            raise ValueError("sample size must be positive")
        if not archives:
            raise ValueError("no requested monthly accounts archives found")
        missing = [str(path) for path, _year, _month in archives if not path.is_file()]
        if missing:
            raise ValueError("archives not found: " + ", ".join(missing))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    results = [inspect_archive(path, year, month, args.sample_size) for path, year, month in archives]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_report(results, args.sample_size), encoding="utf-8")
    print_summary(results)
    print(f"Report written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
