"""Recent-adverse positives sampling (synthetic; no network)."""

from __future__ import annotations

from ukcompany.cli import read_input_numbers
from ukcompany.validation.labels import Label
from ukcompany.validation.sample import sample_positives, write_positives_csv


def _label(case_type: str, month: str) -> Label:
    return Label(case_type, case_type, "unknown", month)


def _labels() -> dict[str, Label]:
    labels = {}
    # Recent adverse across case types and years.
    for i in range(20):
        labels[f"{i:08d}"] = _label("creditors_voluntary_liquidation", "2024-03")
    for i in range(20, 30):
        labels[f"{i:08d}"] = _label("administration", "2023-06")
    # Old adverse (pre-since) -> excluded.
    labels["00000900"] = _label("compulsory_liquidation", "2019-05")
    # Non-adverse -> excluded even though recent.
    labels["00000901"] = _label("other", "2024-01")
    # Missing/blank month -> excluded.
    labels["00000902"] = _label("administration", "")
    return labels


def test_recent_filter_excludes_old_and_includes_new():
    sample = sample_positives(_labels(), n=100, since="2023-01", seed=1)
    assert "00000900" not in sample.numbers  # 2019, before since
    assert "00000902" not in sample.numbers  # no usable month
    assert any(n in sample.numbers for n in ("00000020", "00000029"))  # 2023-06 kept
    assert sample.eligible == 30  # 20 CVL + 10 admin


def test_adverse_only_guard():
    sample = sample_positives(_labels(), n=100, since="2023-01", seed=1)
    assert "00000901" not in sample.numbers  # case_type "other" never sampled
    assert set(sample.by_case_type) <= {
        "creditors_voluntary_liquidation",
        "administration",
    }


def test_cap_and_determinism():
    first = sample_positives(_labels(), n=10, since="2023-01", seed=7)
    second = sample_positives(_labels(), n=10, since="2023-01", seed=7)
    other_seed = sample_positives(_labels(), n=10, since="2023-01", seed=8)
    assert len(first.numbers) == 10  # N respected
    assert first.numbers == second.numbers  # deterministic
    # Different seed usually yields a different draw from a 30-strong pool.
    assert first.numbers != other_seed.numbers
    assert first.shortfall == 0


def test_shortfall_reported_when_fewer_eligible_than_n():
    sample = sample_positives(_labels(), n=500, since="2023-01", seed=1)
    assert len(sample.numbers) == 30  # all eligible taken
    assert sample.shortfall == 470
    assert sum(sample.by_case_type.values()) == 30
    assert sum(sample.by_year.values()) == 30


def test_writer_is_consumable_by_read_input_numbers(tmp_path):
    sample = sample_positives(_labels(), n=5, since="2023-01", seed=3)
    out = tmp_path / "positives.csv"
    write_positives_csv(sample, out)

    header = out.read_text(encoding="utf-8").splitlines()[0]
    assert header == "company_number"
    assert read_input_numbers(str(out)) == sample.numbers
