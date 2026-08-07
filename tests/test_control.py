"""Stratified control drawing (synthetic; no network, no real snapshot)."""

from __future__ import annotations

import json
from datetime import date

import pytest

from ukcompany.snapshot.loader import SnapshotLoader
from ukcompany.validation.control import (
    ControlPlan,
    StratifiedTargets,
    draw_control,
    read_control_csv,
    snapshot_sic_section,
    stratify_targets,
    write_control_csv,
)
from ukcompany.validation.labels import Label, sic_section_from_code

REFERENCE = date(2026, 8, 1)


def test_sic_section_from_code_spot_checks():
    assert sic_section_from_code("01") == "A"
    assert sic_section_from_code("05") == "B"
    assert sic_section_from_code("10") == "C"
    assert sic_section_from_code("41") == "F"  # construction
    assert sic_section_from_code("43") == "F"
    assert sic_section_from_code("47") == "G"  # retail
    assert sic_section_from_code("62") == "J"  # information & communication, NOT C
    assert sic_section_from_code("99") == "U"
    assert sic_section_from_code("5") == "B"  # single digit read as division 5
    assert sic_section_from_code("04") == "unknown"  # gap: no such division
    assert sic_section_from_code("") == "unknown"
    assert sic_section_from_code(None) == "unknown"


def test_snapshot_sic_section_parses_code_label_text():
    assert snapshot_sic_section("62012 - Business and domestic software development") == "J"
    assert snapshot_sic_section("01120 - Growing of rice") == "A"
    assert snapshot_sic_section("99999 - Dormant Company") == "U"
    assert snapshot_sic_section("") == "unknown"
    assert snapshot_sic_section("no code here") == "unknown"
    assert snapshot_sic_section(None) == "unknown"


def _label(section: str, month: str) -> Label:
    return Label("compulsory_liquidation", "Compulsory liquidation", section, month)


def test_stratify_targets_expected_proportions():
    labels = {
        "1": _label("J", "2018-01"),  # 8.6y -> 5-10y
        "2": _label("J", "2019-06"),  # 7.1y -> 5-10y
        "3": _label("F", "2025-06"),  # 1.2y -> <2y
        "4": _label("unknown", ""),  # UNKNOWN band, unknown section
    }
    targets = stratify_targets(labels, REFERENCE)
    assert targets.total == 4
    assert targets.counts == {"J|5-10y": 2, "F|<2y": 1, "unknown|UNKNOWN": 1}
    assert targets.proportions["J|5-10y"] == 0.5


SNAPSHOT_HEADER = "CompanyName,CompanyNumber,CompanyStatus,SICCode.SicText_1,IncorporationDate"
SNAPSHOT_ROWS = [
    "IT ONE,00000001,Active,62020 - IT consultancy,01/01/2018",  # J 5-10y
    "IT TWO,00000002,Active,62090 - Other IT,01/01/2019",  # J 5-10y
    "DATA THREE,00000003,Active,63110 - Data processing,01/06/2017",  # J 5-10y
    "DISSOLVED,00000004,Dissolved,62020 - IT consultancy,01/01/2018",  # non-active -> excluded
    "POSITIVE,00000005,Active,62020 - IT consultancy,01/01/2018",  # in exclude set
    "RETAIL,00000010,Active,47110 - Retail,01/01/2026",  # G <2y (only one)
    "BUILDER,00000099,Active,41100 - Construction,01/01/2018",  # F, not a target stratum
]


def _snapshot_loader(tmp_path) -> SnapshotLoader:
    path = tmp_path / "snapshot.csv"
    path.write_text("\n".join([SNAPSHOT_HEADER, *SNAPSHOT_ROWS]) + "\n", encoding="utf-8")
    return SnapshotLoader(path)


def _targets() -> StratifiedTargets:
    # Two strata, equal weight; n=4 -> target 2 each.
    return StratifiedTargets(counts={"J|5-10y": 1, "G|<2y": 1}, total=2)


def test_draw_control_excludes_filters_and_reports_achieved(tmp_path):
    loader = _snapshot_loader(tmp_path)
    plan = draw_control(
        loader,
        _targets(),
        n=4,
        exclude={"00000005"},
        seed=7,
        reference=REFERENCE,
        snapshot_month="2026-08",
    )
    numbers = set(plan.numbers())

    # Excludes the positive and the dissolved company; ignores the non-target F firm.
    assert "00000005" not in numbers
    assert "00000004" not in numbers
    assert "00000099" not in numbers
    # J stratum has 3 eligible, target 2 -> draws 2 of {1,2,3}; G has 1, target 2 -> under-fills.
    assert numbers <= {"00000001", "00000002", "00000003", "00000010"}
    assert "00000010" in numbers
    assert plan.target_counts == {"J|5-10y": 2, "G|<2y": 2}
    assert plan.achieved_counts == {"J|5-10y": 2, "G|<2y": 1}  # under-fill is visible


def test_draw_control_is_deterministic_by_seed(tmp_path):
    loader = _snapshot_loader(tmp_path)
    first = draw_control(
        loader, _targets(), 4, {"00000005"}, seed=7, reference=REFERENCE, snapshot_month="2026-08"
    )
    second = draw_control(
        loader, _targets(), 4, {"00000005"}, seed=7, reference=REFERENCE, snapshot_month="2026-08"
    )
    assert first.numbers() == second.numbers()


def test_draw_control_empty_targets_draws_nothing(tmp_path):
    loader = _snapshot_loader(tmp_path)
    plan = draw_control(
        loader, StratifiedTargets(), 4, set(), seed=1, reference=REFERENCE, snapshot_month="2026-08"
    )
    assert plan.numbers() == []


def test_two_step_flow_writes_numbers_and_does_not_fetch(tmp_path, monkeypatch):
    # Guard: drawing/writing must never touch the network client.
    import ukcompany.client as client_mod

    def _forbidden(*args, **kwargs):
        raise AssertionError("control drawing must not fetch")

    monkeypatch.setattr(client_mod.CHClient, "__init__", _forbidden)

    loader = _snapshot_loader(tmp_path)
    plan = draw_control(
        loader, _targets(), 4, {"00000005"}, seed=7, reference=REFERENCE, snapshot_month="2026-08"
    )
    out = tmp_path / "control-numbers.csv"
    write_control_csv(plan, out)

    header, *rows = out.read_text(encoding="utf-8").strip().splitlines()
    assert header == "company_number,sic_section,age_band"
    assert len(rows) == len(plan.members)

    sidecar = tmp_path / "control-numbers.csv.strata.json"
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    assert meta["target_counts"] == {"J|5-10y": 2, "G|<2y": 2}
    assert meta["snapshot_month"] == "2026-08"

    # Round-trips back into a ControlPlan carrying strata + provenance.
    reloaded = read_control_csv(out)
    assert reloaded.numbers() == plan.numbers()
    assert reloaded.target_counts == plan.target_counts
    assert {m.age_band for m in reloaded.members} <= {"<2y", "5-10y"}


def test_read_control_csv_tolerates_plain_number_list(tmp_path):
    path = tmp_path / "plain.csv"
    path.write_text("company_number\n00000001\n00000002\n", encoding="utf-8")
    plan = read_control_csv(path)
    assert plan.numbers() == ["00000001", "00000002"]
    assert all(m.sic_section == "unknown" and m.age_band == "UNKNOWN" for m in plan.members)
    assert isinstance(plan, ControlPlan)


@pytest.mark.parametrize(
    "month,expected", [("2018-01", "5-10y"), ("2025-06", "<2y"), ("", "UNKNOWN")]
)
def test_stratify_bands_match_expectations(month, expected):
    targets = stratify_targets({"1": _label("J", month)}, REFERENCE)
    (stratum,) = targets.counts
    assert stratum.split("|")[1] == expected
