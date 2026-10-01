"""Recon over ALL parts of the Companies House PSC bulk snapshot.

Streams every psc-snapshot-*_kofN.txt part matched by --parts and writes aggregate-only
results to docs/recon-psc-results.json plus a rendered docs/recon-psc-results.md.
No per-record output; no name, name_elements, address lines, or date_of_birth values are
ever written. See docs/recon-psc.md for the brief this implements.

Usage:
    python scripts/recon_psc.py \
        --parts '/path/psc-snapshot-2026-09-18_*of32.txt' \
        --company-csv 'data/snapshot/2026-08/extracted/*/*.csv'
"""

from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

PART_RE = re.compile(r"psc-snapshot-(\d{4}-\d{2}-\d{2})_(\d+)of(\d+)\.txt$")
PSC_REGIME_START = "2016-04-06"

# Raw match: value exactly as supplied, canonical uppercase with zero or one internal space.
POSTCODE_RAW_RE = re.compile(r"(GIR ?0AA|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2})")
# Normalised match: after upper() and removing ALL whitespace.
POSTCODE_NORM_RE = re.compile(r"(GIR0AA|[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2})")
REGNUM_RE = re.compile(r"[A-Z0-9]{8}")

# Normalisation map for the UK share of country-like fields. A value is UK when its
# lower-cased, whitespace-collapsed, trailing-dot-stripped form is in this set.
UK_COUNTRY_VALUES = frozenset(
    {
        "england",
        "scotland",
        "wales",
        "cymru",
        "northern ireland",
        "n ireland",
        "n. ireland",
        "northern-ireland",
        "united kingdom",
        "uk",
        "u.k",
        "u.k.",
        "gb",
        "great britain",
        "britain",
        "england and wales",
        "england & wales",
        "united kingdom of great britain and northern ireland",
    }
)

NOC_SUFFIXES = (
    "-as-firm",
    "-as-trust",
    "-limited-liability-partnership",
    "-registered-overseas-entity",
)

TOP_KEY_BUCKETS = (1, 2, 3, 4, 5)


def norm_country(value: str) -> str:
    return " ".join(value.strip().lower().rstrip(".").split())


def is_uk(value: str) -> bool:
    return norm_country(value) in UK_COUNTRY_VALUES


def norm_postcode(value: str) -> str:
    return "".join(value.split()).upper()


def key_hash(*parts: object) -> int:
    text = "|".join(str(part) for part in parts)
    return int.from_bytes(hashlib.blake2b(text.encode(), digest_size=8).digest(), "big")


def bucket(count: int) -> str:
    if count <= 5:
        return str(count)
    if count <= 10:
        return "6-10"
    if count <= 50:
        return "11-50"
    return "51+"


def top_counter(counter: Counter, n: int) -> dict[str, int]:
    ranked = sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:n]
    return dict(ranked)


def sorted_counter(counter: Counter) -> dict:
    return {str(key): counter[key] for key in sorted(counter, key=str)}


class PartStats:
    """Counters collected identically per part and for the overall roll-up."""

    def __init__(self) -> None:
        self.n_records = 0
        self.n_bad_lines = 0
        self.bad_line_reasons: Counter = Counter()
        self.top_keys: Counter = Counter()
        self.data_keys: Counter = Counter()
        self.kinds: Counter = Counter()
        self.kind_contains_statement = 0
        self.data_key_contains_statement = 0
        self.statement_like = 0
        self.statement_like_kinds: Counter = Counter()
        self.statement_like_descriptions: Counter = Counter()
        self.notified_present = 0
        self.notified_years: Counter = Counter()
        self.notified_min: str | None = None
        self.notified_max: str | None = None
        self.pre_regime_notified = 0
        self.ceased_present = 0
        self.ceased_years: Counter = Counter()
        self.ceased_min: str | None = None
        self.ceased_max: str | None = None
        self.ceased_before_notified = 0
        self.ceased_flag_values: Counter = Counter()
        self.crosstab: Counter = Counter()  # (notified year, ceased bool)
        self.prefixes: Counter = Counter()
        self.company_min: str | None = None
        self.company_max: str | None = None
        self.company_monotonic = True
        self._company_prev: str | None = None
        # Individuals.
        self.n_individual = 0
        self.dob_year_present = 0
        self.dob_month_present = 0
        self.yob_bands: Counter = Counter()
        self.age_lt16 = 0
        self.age_gt110 = 0
        self.nationality_present = 0
        self.nationality: Counter = Counter()
        self.cor_present = 0
        self.cor: Counter = Counter()
        self.cor_uk = 0
        self.addr_country_present = 0
        self.addr_country: Counter = Counter()
        self.addr_country_uk = 0
        self.pc_present = 0
        self.pc_raw_match = 0
        self.pc_norm_match = 0
        self.pc_join = 0
        self.pc_join_with_ro_pc = 0
        self.pc_equal_ro = 0
        self.ivd_present = 0
        self.ivd_start_years: Counter = Counter()
        self.sanctioned_present = 0
        self.sanctioned_values: Counter = Counter()
        self.person_key_complete = 0
        # Corporate / legal-person.
        self.n_corporate = 0
        self.ident_present = 0
        self.ident_keys: Counter = Counter()
        self.regnum_present = 0
        self.regnum_8char = 0
        self.regnum_resolved = 0
        self.country_registered_present = 0
        self.country_registered: Counter = Counter()
        self.country_registered_uk = 0
        self.legal_form: Counter = Counter()
        # Natures of control.
        self.noc_records = 0
        self.noc_total = 0
        self.nocs: Counter = Counter()

    def update(self, record: dict, company_map: dict[str, str]) -> None:
        self.n_records += 1
        for key in record:
            self.top_keys[key] += 1
        data = record.get("data") or {}
        company = str(record.get("company_number") or "")
        for key in data:
            self.data_keys[key] += 1
            if "statement" in key:
                self.data_key_contains_statement += 1
        links = data.get("links")
        if isinstance(links, dict):
            for key in links:
                self.data_keys[f"links.{key}"] += 1
                if "statement" in key:
                    self.data_key_contains_statement += 1
        kind = str(data.get("kind") or "<missing>")
        self.kinds[kind] += 1
        if "statement" in kind:
            self.kind_contains_statement += 1

        notified = data.get("notified_on")
        ceased_on = data.get("ceased_on")
        ceased_flag = data.get("ceased")
        if ceased_flag is not None:
            self.ceased_flag_values[str(ceased_flag)] += 1
        if notified is None and ("description" in data or "ceased" in data):
            self.statement_like += 1
            self.statement_like_kinds[kind] += 1
            self.statement_like_descriptions[str(data.get("description"))[:80]] += 1

        notified_year = None
        if notified is not None:
            notified = str(notified)
            self.notified_present += 1
            if self.notified_min is None or notified < self.notified_min:
                self.notified_min = notified
            if self.notified_max is None or notified > self.notified_max:
                self.notified_max = notified
            if notified < PSC_REGIME_START:
                self.pre_regime_notified += 1
            year = notified[:4]
            if year.isdigit():
                notified_year = year
                self.notified_years[year] += 1
        if ceased_on is not None:
            ceased_on = str(ceased_on)
            self.ceased_present += 1
            if self.ceased_min is None or ceased_on < self.ceased_min:
                self.ceased_min = ceased_on
            if self.ceased_max is None or ceased_on > self.ceased_max:
                self.ceased_max = ceased_on
            year = ceased_on[:4]
            if year.isdigit():
                self.ceased_years[year] += 1
            if notified is not None and ceased_on < notified:
                self.ceased_before_notified += 1
        if notified_year is not None:
            self.crosstab[(notified_year, ceased_on is not None)] += 1

        if company:
            self.prefixes[company[:2]] += 1
            if self.company_min is None or company < self.company_min:
                self.company_min = company
            if self.company_max is None or company > self.company_max:
                self.company_max = company
            if self._company_prev is not None and company < self._company_prev:
                self.company_monotonic = False
            self._company_prev = company

        nocs = data.get("natures_of_control")
        if isinstance(nocs, list) and nocs:
            self.noc_records += 1
            self.noc_total += len(nocs)
            for noc in nocs:
                self.nocs[str(noc)] += 1

        if kind.startswith("individual"):
            self._update_individual(data, company, company_map, notified)
        elif kind.startswith("corporate") or kind.startswith("legal-person"):
            self._update_corporate(data, company_map)

    def _update_individual(
        self,
        data: dict,
        company: str,
        company_map: dict[str, str],
        notified: str | None,
    ) -> None:
        self.n_individual += 1
        dob = data.get("date_of_birth") or {}
        year = dob.get("year")
        month = dob.get("month")
        if isinstance(year, int):
            self.dob_year_present += 1
            band_low = year - year % 5
            self.yob_bands[f"{band_low}-{band_low + 4}"] += 1
            if notified is not None and notified[:4].isdigit():
                age = int(notified[:4]) - year
                if isinstance(month, int) and len(notified) >= 7 and notified[5:7].isdigit():
                    if int(notified[5:7]) < month:
                        age -= 1
                if age < 16:
                    self.age_lt16 += 1
                elif age > 110:
                    self.age_gt110 += 1
        if isinstance(month, int):
            self.dob_month_present += 1

        nationality = data.get("nationality")
        if nationality is not None and str(nationality).strip():
            self.nationality_present += 1
            self.nationality[str(nationality).strip().title()] += 1
        cor = data.get("country_of_residence")
        if cor is not None and str(cor).strip():
            self.cor_present += 1
            self.cor[str(cor).strip().title()] += 1
            if is_uk(str(cor)):
                self.cor_uk += 1
        address = data.get("address") or {}
        addr_country = address.get("country")
        if addr_country is not None and str(addr_country).strip():
            self.addr_country_present += 1
            self.addr_country[str(addr_country).strip().title()] += 1
            if is_uk(str(addr_country)):
                self.addr_country_uk += 1
        postcode = address.get("postal_code")
        if postcode is not None and str(postcode).strip():
            postcode = str(postcode)
            self.pc_present += 1
            if POSTCODE_RAW_RE.fullmatch(postcode):
                self.pc_raw_match += 1
            normalised = norm_postcode(postcode)
            if POSTCODE_NORM_RE.fullmatch(normalised):
                self.pc_norm_match += 1
            if company in company_map:
                self.pc_join += 1
                ro_pc = company_map[company]
                if ro_pc:
                    self.pc_join_with_ro_pc += 1
                    if normalised == ro_pc:
                        self.pc_equal_ro += 1

        ivd = data.get("identity_verification_details")
        if isinstance(ivd, dict):
            self.ivd_present += 1
            start = str(ivd.get("appointment_verification_start_on") or "")
            if start[:4].isdigit():
                self.ivd_start_years[start[:4]] += 1
        sanctioned = data.get("is_sanctioned")
        if sanctioned is not None:
            self.sanctioned_present += 1
            self.sanctioned_values[str(sanctioned)] += 1

        elements = data.get("name_elements") or {}
        forename = elements.get("forename")
        surname = elements.get("surname")
        if forename and surname and isinstance(year, int) and isinstance(month, int):
            self.person_key_complete += 1

    def _update_corporate(self, data: dict, company_map: dict[str, str]) -> None:
        self.n_corporate += 1
        identification = data.get("identification")
        if isinstance(identification, dict):
            self.ident_present += 1
            for key in identification:
                self.ident_keys[key] += 1
            regnum = identification.get("registration_number")
            if regnum is not None and str(regnum).strip():
                self.regnum_present += 1
                cleaned = str(regnum).strip().upper()
                if REGNUM_RE.fullmatch(cleaned):
                    self.regnum_8char += 1
                if cleaned in company_map or (
                    cleaned.isdigit() and len(cleaned) <= 8 and cleaned.zfill(8) in company_map
                ):
                    self.regnum_resolved += 1
            country = identification.get("country_registered")
            if country is not None and str(country).strip():
                self.country_registered_present += 1
                self.country_registered[str(country).strip().title()] += 1
                if is_uk(str(country)):
                    self.country_registered_uk += 1
            form = identification.get("legal_form")
            if form is not None and str(form).strip():
                self.legal_form[" ".join(str(form).split()).lower()] += 1

    def absorb(self, other: PartStats) -> None:
        for name, value in vars(other).items():
            if name.startswith("_"):
                continue
            mine = getattr(self, name)
            if isinstance(value, Counter):
                mine.update(value)
            elif isinstance(value, int):
                setattr(self, name, mine + value)
        for name in ("notified_min", "ceased_min", "company_min"):
            self._merge_extreme(other, name, take_smaller=True)
        for name in ("notified_max", "ceased_max", "company_max"):
            self._merge_extreme(other, name, take_smaller=False)
        # Monotonicity and the bool flags above are per-part notions; the overall
        # roll-up reports them as "all parts monotonic".
        self.company_monotonic = self.company_monotonic and other.company_monotonic

    def _merge_extreme(self, other: PartStats, name: str, *, take_smaller: bool) -> None:
        mine, theirs = getattr(self, name), getattr(other, name)
        if theirs is None:
            return
        if mine is None or (theirs < mine if take_smaller else theirs > mine):
            setattr(self, name, theirs)

    def crosstab_table(self) -> dict[str, dict[str, int]]:
        years = sorted({year for year, _ceased in self.crosstab})
        return {
            year: {
                "not_ceased": self.crosstab.get((year, False), 0),
                "ceased": self.crosstab.get((year, True), 0),
            }
            for year in years
        }

    def noc_families(self) -> tuple[dict[str, int], int]:
        families: Counter = Counter()
        bases: set[str] = set()
        for noc, count in self.nocs.items():
            family = "plain"
            base = noc
            for suffix in NOC_SUFFIXES:
                if noc.endswith(suffix):
                    family = suffix
                    base = noc[: -len(suffix)]
                    break
            families[family] += count
            bases.add(base)
        return sorted_counter(families), len(bases)

    def emit(self, *, vocab: bool) -> dict:
        families, distinct_bases = self.noc_families()
        result = {
            "n_records": self.n_records,
            "n_bad_lines": self.n_bad_lines,
            "bad_line_reasons": sorted_counter(self.bad_line_reasons),
            "top_level_keys": sorted_counter(self.top_keys),
            "data_keys": sorted_counter(self.data_keys),
            "kinds": sorted_counter(self.kinds),
            "statements": {
                "kind_contains_statement": self.kind_contains_statement,
                "data_key_contains_statement": self.data_key_contains_statement,
                "statement_like_records": self.statement_like,
                "statement_like_kinds": sorted_counter(self.statement_like_kinds),
                "statement_like_descriptions": sorted_counter(self.statement_like_descriptions),
                "ceased_flag_values": sorted_counter(self.ceased_flag_values),
            },
            "notified_on": {
                "present": self.notified_present,
                "min": self.notified_min,
                "max": self.notified_max,
                "years": sorted_counter(self.notified_years),
                "pre_regime": self.pre_regime_notified,
            },
            "ceased_on": {
                "present": self.ceased_present,
                "min": self.ceased_min,
                "max": self.ceased_max,
                "years": sorted_counter(self.ceased_years),
                "before_notified": self.ceased_before_notified,
            },
            "notified_year_x_ceased": self.crosstab_table(),
            "company_number": {
                "prefixes": sorted_counter(self.prefixes),
                "min": self.company_min,
                "max": self.company_max,
                "monotonic_in_file": self.company_monotonic,
            },
            "individuals": {
                "n": self.n_individual,
                "dob_year_present": self.dob_year_present,
                "dob_month_present": self.dob_month_present,
                "age_under_16_at_notified": self.age_lt16,
                "age_over_110_at_notified": self.age_gt110,
                "nationality_present": self.nationality_present,
                "country_of_residence_present": self.cor_present,
                "country_of_residence_uk": self.cor_uk,
                "address_country_present": self.addr_country_present,
                "address_country_uk": self.addr_country_uk,
                "postcode_present": self.pc_present,
                "postcode_raw_match": self.pc_raw_match,
                "postcode_norm_match": self.pc_norm_match,
                "postcode_company_join": self.pc_join,
                "postcode_company_join_with_ro_postcode": self.pc_join_with_ro_pc,
                "postcode_equals_registered_office": self.pc_equal_ro,
                "identity_verification_present": self.ivd_present,
                "identity_verification_start_years": sorted_counter(self.ivd_start_years),
                "is_sanctioned_present": self.sanctioned_present,
                "is_sanctioned_values": sorted_counter(self.sanctioned_values),
                "person_key_complete": self.person_key_complete,
            },
            "corporate": {
                "n": self.n_corporate,
                "identification_present": self.ident_present,
                "identification_keys": sorted_counter(self.ident_keys),
                "registration_number_present": self.regnum_present,
                "registration_number_8char": self.regnum_8char,
                "registration_number_resolved": self.regnum_resolved,
                "country_registered_present": self.country_registered_present,
                "country_registered_uk": self.country_registered_uk,
            },
            "natures_of_control": {
                "records_with_any": self.noc_records,
                "total": self.noc_total,
                "families": families,
                "distinct_base_rights": distinct_bases,
            },
        }
        if vocab:
            result["individuals"]["yob_5yr_bands"] = sorted_counter(self.yob_bands)
            result["individuals"]["nationality_distinct_raw"] = len(self.nationality)
            result["individuals"]["nationality_top30"] = top_counter(self.nationality, 30)
            result["individuals"]["country_of_residence_top30"] = top_counter(self.cor, 30)
            result["individuals"]["address_country_top30"] = top_counter(self.addr_country, 30)
            result["corporate"]["country_registered_top30"] = top_counter(
                self.country_registered, 30
            )
            result["corporate"]["legal_form_top20"] = top_counter(self.legal_form, 20)
            result["natures_of_control"]["vocabulary"] = sorted_counter(self.nocs)
        return result


def load_company_map(pattern: str) -> tuple[dict[str, str], int, list[str]]:
    """CompanyNumber -> normalised RegAddress.PostCode ('' when absent) from the snapshot."""
    paths = sorted(glob.glob(pattern))
    if not paths:
        raise SystemExit(f"no general-snapshot CSVs match: {pattern}")
    mapping: dict[str, str] = {}
    rows = 0
    for path in paths:
        with open(path, newline="", encoding="utf-8", errors="replace") as handle:
            reader = csv.reader(handle)
            header = [name.strip() for name in next(reader, [])]
            try:
                number_idx = header.index("CompanyNumber")
                postcode_idx = header.index("RegAddress.PostCode")
            except ValueError as exc:
                raise SystemExit(f"unexpected snapshot header in {path}") from exc
            for row in reader:
                if len(row) <= max(number_idx, postcode_idx):
                    continue
                number = row[number_idx].strip().upper()
                if not number:
                    continue
                mapping[number] = norm_postcode(row[postcode_idx])
                rows += 1
    return mapping, rows, [Path(path).name for path in paths]


def discover_parts(pattern: str) -> tuple[str, int, list[tuple[int, str]]]:
    parts = []
    dates = set()
    totals = set()
    for path in sorted(glob.glob(pattern)):
        match = PART_RE.search(Path(path).name)
        if not match:
            continue
        date, k, total = match.group(1), int(match.group(2)), int(match.group(3))
        dates.add(date)
        totals.add(total)
        parts.append((k, path))
    if not parts:
        raise SystemExit(f"no PSC snapshot parts match: {pattern}")
    if len(dates) > 1:
        raise SystemExit(f"refusing to mix snapshot dates: {sorted(dates)}")
    if len(totals) > 1:
        raise SystemExit(f"inconsistent part totals in filenames: {sorted(totals)}")
    expected = totals.pop()
    found = {k for k, _path in parts}
    missing = sorted(set(range(1, expected + 1)) - found)
    if missing:
        raise SystemExit(f"missing parts {missing} of {expected}; run over ALL parts")
    return dates.pop(), expected, sorted(parts)


def infer_partition_rule(per_part: dict[str, dict]) -> str:
    ranges = []
    for name in per_part:
        block = per_part[name]["company_number"]
        if block["min"] is None:
            return "not evident (a part had no company numbers)"
        ranges.append((block["min"], block["max"], name, block["monotonic_in_file"]))
    ranges.sort()
    disjoint = all(ranges[i][1] <= ranges[i + 1][0] for i in range(len(ranges) - 1))
    monotonic = all(item[3] for item in ranges)
    if disjoint and monotonic:
        return (
            "parts hold disjoint, internally sorted company-number ranges "
            "(lexicographic split of one company-number-ordered extract)"
        )
    if disjoint:
        return "parts hold disjoint company-number ranges (not sorted within parts)"
    return "not evident (per-part company-number ranges overlap)"


def run_recon(args: argparse.Namespace) -> dict:
    started = time.monotonic()
    snapshot_date, expected, parts = discover_parts(args.parts)
    company_map, company_rows, company_files = load_company_map(args.company_csv)
    print(f"company map loaded: {len(company_map):,} companies", flush=True)

    overall = PartStats()
    per_part: dict[str, dict] = {}
    company_pack: dict[str, int] = {}
    key_records: dict[int, int] = {}
    key_first_company: dict[int, int] = {}
    key_companies: dict[int, set[int]] = {}

    for k, path in parts:
        part = PartStats()
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, 1):
                if args.max_lines_per_part and line_number > args.max_lines_per_part:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    part.n_bad_lines += 1
                    part.bad_line_reasons["json_decode_error"] += 1
                    continue
                if not isinstance(record, dict) or not isinstance(record.get("data"), dict):
                    part.n_bad_lines += 1
                    part.bad_line_reasons["not_an_object_with_data"] += 1
                    continue
                part.update(record, company_map)

                data = record["data"]
                company = str(record.get("company_number") or "")
                if company:
                    active = data.get("ceased_on") is None and data.get("ceased") is not True
                    packed = company_pack.get(company, 0)
                    all_count = packed & 0xFFF
                    active_count = (packed >> 12) & 0xFFF
                    flags = packed >> 24
                    all_count = min(all_count + 1, 0xFFF)
                    if active:
                        active_count = min(active_count + 1, 0xFFF)
                    kind = str(data.get("kind") or "")
                    if kind.startswith("individual"):
                        flags |= 1
                    elif kind.startswith("corporate") or kind.startswith("legal-person"):
                        flags |= 2
                    company_pack[company] = all_count | (active_count << 12) | (flags << 24)

                kind = str(data.get("kind") or "")
                if kind.startswith("individual"):
                    elements = data.get("name_elements") or {}
                    forename = elements.get("forename")
                    surname = elements.get("surname")
                    dob = data.get("date_of_birth") or {}
                    year, month = dob.get("year"), dob.get("month")
                    if forename and surname and isinstance(year, int) and isinstance(month, int):
                        person = key_hash(
                            str(forename).strip().lower(),
                            str(surname).strip().lower(),
                            year,
                            month,
                        )
                        key_records[person] = key_records.get(person, 0) + 1
                        company_h = key_hash(company)
                        known = key_companies.get(person)
                        if known is not None:
                            known.add(company_h)
                        else:
                            first = key_first_company.get(person)
                            if first is None:
                                key_first_company[person] = company_h
                            elif first != company_h:
                                key_companies[person] = {first, company_h}
                                del key_first_company[person]
        name = f"{k}of{expected}"
        per_part[name] = part.emit(vocab=False)
        overall.absorb(part)
        print(
            f"[{k}/{expected}] {Path(path).name}: {part.n_records:,} records, "
            f"{part.n_bad_lines} bad lines",
            flush=True,
        )

    records_per_key: Counter = Counter()
    for count in key_records.values():
        records_per_key[bucket(count)] += 1
    companies_per_key: Counter = Counter()
    for person in key_records:
        known = key_companies.get(person)
        companies_per_key[bucket(len(known) if known is not None else 1)] += 1
    multi_record_keys = sum(
        count for label, count in records_per_key.items() if label != "1"
    )
    multi_company_keys = sum(
        count for label, count in companies_per_key.items() if label != "1"
    )

    psc_all: Counter = Counter()
    psc_active: Counter = Counter()
    ceased_only = 0
    has_individual = 0
    has_corporate = 0
    mixed = 0
    for packed in company_pack.values():
        all_count = packed & 0xFFF
        active_count = (packed >> 12) & 0xFFF
        flags = packed >> 24
        psc_all[bucket(all_count)] += 1
        psc_active[bucket(active_count)] += 1
        if active_count == 0:
            ceased_only += 1
        if flags & 1:
            has_individual += 1
        if flags & 2:
            has_corporate += 1
        if flags & 3 == 3:
            mixed += 1

    result = {
        "snapshot_date": snapshot_date,
        "n_parts": len(parts),
        "n_parts_expected": expected,
        "n_records": overall.n_records,
        "n_bad_lines": overall.n_bad_lines,
        "runtime_seconds": round(time.monotonic() - started, 1),
        "generated_by": "scripts/recon_psc.py",
        "inputs": {
            "parts_glob": args.parts,
            "company_snapshot_files": company_files,
            "company_snapshot_rows": company_rows,
            "company_snapshot_distinct": len(company_map),
        },
        "normalisation": {
            "uk_country_values": sorted(UK_COUNTRY_VALUES),
            "country_normalisation": "lower-case, collapse whitespace, strip trailing dots",
            "postcode_raw_regex": POSTCODE_RAW_RE.pattern,
            "postcode_norm_regex": POSTCODE_NORM_RE.pattern,
            "postcode_normalisation": "upper-case and remove all whitespace",
            "registration_number_resolution": (
                "strip/upper, then direct lookup in the general snapshot; digit-only values "
                "of length <= 8 are also tried zero-padded to 8"
            ),
            "active_definition": "no ceased_on and data.ceased is not true",
            "ceased_in_crosstab": "presence of ceased_on",
            "person_key": "(forename lower, surname lower, dob year, dob month), blake2b-64",
        },
        "overall": overall.emit(vocab=True),
        "companies": {
            "distinct": len(company_pack),
            "pscs_per_company_all": sorted_counter(psc_all),
            "pscs_per_company_active": sorted_counter(psc_active),
            "only_ceased_records": ceased_only,
            "with_individual_psc": has_individual,
            "with_corporate_psc": has_corporate,
            "with_both": mixed,
        },
        "person_keys": {
            "complete_key_records": sum(key_records.values()),
            "distinct_keys": len(key_records),
            "records_per_key": sorted_counter(records_per_key),
            "keys_on_multiple_records": multi_record_keys,
            "distinct_companies_per_key": sorted_counter(companies_per_key),
            "keys_on_multiple_companies": multi_company_keys,
        },
        "per_part": per_part,
    }
    result["partition_rule"] = infer_partition_rule(per_part)
    if args.max_lines_per_part:
        result["WARNING"] = (
            f"DEVELOPMENT RUN truncated at {args.max_lines_per_part} lines per part; "
            "numbers are NOT citable"
        )
    return result


def pct(numerator: int, denominator: int) -> str:
    return f"{100 * numerator / denominator:.1f}%" if denominator else "n/a"


def render_markdown(result: dict) -> str:
    overall = result["overall"]
    individuals = overall["individuals"]
    corporate = overall["corporate"]
    companies = result["companies"]
    keys = result["person_keys"]
    n = result["n_records"]
    n_individual = individuals["n"]
    lines = [
        "# PSC bulk snapshot recon results",
        "",
        "Generated by `scripts/recon_psc.py`; every number below is a field in",
        "`docs/recon-psc-results.json`. Aggregates only; no personal data.",
        "",
        f"- Snapshot date: **{result['snapshot_date']}**",
        f"- Parts: {result['n_parts']} of {result['n_parts_expected']}",
        f"- Records: {n:,}; bad lines: {result['n_bad_lines']:,}",
        f"- Runtime: {result['runtime_seconds']:,.0f} s",
        f"- Company join base: {result['inputs']['company_snapshot_distinct']:,} companies "
        f"({', '.join(result['inputs']['company_snapshot_files'][:1])}…)",
    ]
    if "WARNING" in result:
        lines += ["", f"**{result['WARNING']}**"]
    lines += ["", "## Kinds", "", "| kind | records | share |", "|---|---:|---:|"]
    for kind, count in sorted(overall["kinds"].items(), key=lambda item: -item[1]):
        lines.append(f"| `{kind}` | {count:,} | {pct(count, n)} |")
    statements = overall["statements"]
    lines += [
        "",
        "## Statement records",
        "",
        f"- Kinds containing `statement`: {statements['kind_contains_statement']:,}",
        f"- Data/links keys containing `statement`: "
        f"{statements['data_key_contains_statement']:,}",
        f"- Statement-like records (description/ceased, no `notified_on`): "
        f"{statements['statement_like_records']:,}",
        f"- Their kinds: `{statements['statement_like_kinds']}`",
    ]
    notified = overall["notified_on"]
    ceased = overall["ceased_on"]
    lines += [
        "",
        "## Time structure",
        "",
        f"- `notified_on` present: {notified['present']:,} ({pct(notified['present'], n)}); "
        f"range {notified['min']} – {notified['max']}; "
        f"pre-regime (< 2016-04-06): {notified['pre_regime']:,}",
        f"- `ceased_on` present: {ceased['present']:,} ({pct(ceased['present'], n)}); "
        f"range {ceased['min']} – {ceased['max']}; "
        f"ceased before notified: {ceased['before_notified']:,}",
        "",
        "| notified year | not ceased | ceased |",
        "|---|---:|---:|",
    ]
    for year, row in overall["notified_year_x_ceased"].items():
        lines.append(f"| {year} | {row['not_ceased']:,} | {row['ceased']:,} |")
    lines += [
        "",
        "## Companies",
        "",
        f"- Distinct companies: {companies['distinct']:,}",
        f"- Only-ceased-records companies: {companies['only_ceased_records']:,}",
        f"- With >=1 individual PSC: {companies['with_individual_psc']:,}; "
        f"corporate: {companies['with_corporate_psc']:,}; both: {companies['with_both']:,}",
        f"- PSCs per company (all): `{companies['pscs_per_company_all']}`",
        f"- PSCs per company (active): `{companies['pscs_per_company_active']}`",
        "",
        "## Individuals",
        "",
        f"- Individual records: {n_individual:,} ({pct(n_individual, n)})",
        f"- DOB year present: {pct(individuals['dob_year_present'], n_individual)}; "
        f"month present: {pct(individuals['dob_month_present'], n_individual)}",
        f"- Implied age at notification < 16: {individuals['age_under_16_at_notified']:,}; "
        f"> 110: {individuals['age_over_110_at_notified']:,}",
        f"- Nationality present: {pct(individuals['nationality_present'], n_individual)}; "
        f"distinct raw values: {individuals['nationality_distinct_raw']:,}",
        f"- Country of residence present: {pct(individuals['country_of_residence_present'], n_individual)}; "
        f"UK share of present: "
        f"{pct(individuals['country_of_residence_uk'], individuals['country_of_residence_present'])}",
        f"- Address country present: {pct(individuals['address_country_present'], n_individual)}; "
        f"UK share of present: "
        f"{pct(individuals['address_country_uk'], individuals['address_country_present'])}",
        f"- Service postcode present: {pct(individuals['postcode_present'], n_individual)}; "
        f"UK-format raw: {pct(individuals['postcode_raw_match'], individuals['postcode_present'])}; "
        f"after normalisation: "
        f"{pct(individuals['postcode_norm_match'], individuals['postcode_present'])}",
        f"- Postcode-bearing records joined to general snapshot: "
        f"{pct(individuals['postcode_company_join'], individuals['postcode_present'])}; "
        f"service = registered-office postcode: "
        f"{pct(individuals['postcode_equals_registered_office'], individuals['postcode_company_join_with_ro_postcode'])} "
        f"(of {individuals['postcode_company_join_with_ro_postcode']:,} joined-with-RO-postcode)",
        f"- Identity verification present: {pct(individuals['identity_verification_present'], n_individual)}; "
        f"start years: `{individuals['identity_verification_start_years']}`",
        f"- `is_sanctioned` present: {individuals['is_sanctioned_present']:,}; "
        f"values: `{individuals['is_sanctioned_values']}`",
        "",
        "### Person-key connectivity (overall, all parts)",
        "",
        f"- Records with a complete key: {keys['complete_key_records']:,} of {n_individual:,}",
        f"- Distinct keys: {keys['distinct_keys']:,}",
        f"- Keys on >=2 records: {keys['keys_on_multiple_records']:,} "
        f"({pct(keys['keys_on_multiple_records'], keys['distinct_keys'])})",
        f"- Keys on >=2 distinct companies: {keys['keys_on_multiple_companies']:,} "
        f"({pct(keys['keys_on_multiple_companies'], keys['distinct_keys'])})",
        f"- Records per key: `{keys['records_per_key']}`",
        f"- Companies per key: `{keys['distinct_companies_per_key']}`",
        "",
        "## Corporate PSCs",
        "",
        f"- Corporate/legal-person records: {corporate['n']:,}",
        f"- `identification` present: {pct(corporate['identification_present'], corporate['n'])}; "
        f"sub-keys: `{corporate['identification_keys']}`",
        f"- `registration_number` present: {corporate['registration_number_present']:,}; "
        f"8-char [A-Z0-9]: "
        f"{pct(corporate['registration_number_8char'], corporate['registration_number_present'])}; "
        f"resolves to a general-snapshot company: "
        f"{pct(corporate['registration_number_resolved'], corporate['registration_number_present'])}",
        f"- `country_registered` present: {corporate['country_registered_present']:,}; "
        f"UK share of present: "
        f"{pct(corporate['country_registered_uk'], corporate['country_registered_present'])}",
        "",
        "## Natures of control",
        "",
        f"- Records with any: {overall['natures_of_control']['records_with_any']:,}; "
        f"total assertions: {overall['natures_of_control']['total']:,}",
        f"- Distinct base rights after suffix stripping: "
        f"{overall['natures_of_control']['distinct_base_rights']}",
        f"- Families: `{overall['natures_of_control']['families']}`",
        "",
        "## Partitioning",
        "",
        f"**Rule: {result['partition_rule']}**",
        "",
        "| part | records | company min | company max | sorted | top notified years |",
        "|---|---:|---|---|---|---|",
    ]
    for name, block in result["per_part"].items():
        company_block = block["company_number"]
        top_years = top_counter(Counter(block["notified_on"]["years"]), 3)
        lines.append(
            f"| {name} | {block['n_records']:,} | `{company_block['min']}` | "
            f"`{company_block['max']}` | {company_block['monotonic_in_file']} | "
            f"`{top_years}` |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parts", required=True, help="glob of psc-snapshot part .txt files")
    parser.add_argument(
        "--company-csv",
        default="data/snapshot/2026-08/extracted/*/*.csv",
        help="glob of general-snapshot BasicCompanyData CSVs",
    )
    parser.add_argument("--json", default="docs/recon-psc-results.json")
    parser.add_argument("--md", default="docs/recon-psc-results.md")
    parser.add_argument(
        "--max-lines-per-part",
        type=int,
        default=0,
        help="DEVELOPMENT ONLY: truncate each part; output is watermarked non-citable",
    )
    args = parser.parse_args()
    result = run_recon(args)
    json_path = Path(args.json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=1, sort_keys=False), encoding="utf-8")
    Path(args.md).write_text(render_markdown(result), encoding="utf-8")
    print(f"JSON: {json_path}")
    print(f"MD: {args.md}")
    print(f"Runtime: {result['runtime_seconds']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
