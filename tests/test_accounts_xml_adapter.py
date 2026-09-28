import pytest

from ukcompany.accounts.core import ContextKind
from ukcompany.accounts.xml_adapter import _classify_segments, extract_filing_xml

NS = (
    'xmlns="http://www.xbrl.org/2003/instance" '
    'xmlns:xbrli="http://www.xbrl.org/2003/instance" '
    'xmlns:xbrldi="http://xbrl.org/2006/xbrldi" '
    'xmlns:iso4217="http://www.xbrl.org/2003/iso4217" '
    'xmlns:uk="http://example.com/uk"'
)


def xbrl(*body: str) -> bytes:
    """Minimal plain-XBRL instance document, matching the real structure a Companies House
    `.xml` member uses (confirmed against a real sample,
    Prod224_0016_08317102_20141231.xml): unprefixed context/unit/period elements directly
    under the xbrl root, no ix:resources wrapper (that's iXBRL-only)."""
    contexts = """
      <context id="current"><entity><identifier scheme="test">1</identifier></entity>
        <period><instant>2023-12-31</instant></period></context>
      <unit id="GBP"><measure>iso4217:GBP</measure></unit>
    """
    return (f"<xbrl {NS}>" + contexts + "".join(body) + "</xbrl>").encode()


def fact(concept: str, value: str, *, context: str = "current", unit: str = "GBP", extra: str = "") -> str:
    return f'<uk:{concept} contextRef="{context}" unitRef="{unit}" {extra}>{value}</uk:{concept}>'


def test_basic_numeric_and_nonnumeric_extraction_records_ixbrlparse_provenance() -> None:
    data = xbrl(
        fact("Equity", "500"),
        '<uk:EntityTradingStatus contextRef="current">Active</uk:EntityTradingStatus>',
    )
    result = extract_filing_xml(data, "1", "20231231")

    assert [(row.concept, row.fact_kind, row.numeric_value, row.raw_value) for row in result.observations] == [
        ("Equity", "numeric", "500", "500"),
        ("EntityTradingStatus", "non-numeric", None, "Active"),
    ]
    assert {row.parser for row in result.observations} == {"ixbrlparse"}
    assert result.integrity.closes()


def test_scale_and_sign_are_not_reapplied_on_top_of_ixbrlparse() -> None:
    """ixbrlparse's own format transform already multiplies by 10**scale and applies the
    sign internally (confirmed by reading ixbrlparse/components/_base.py's parse_value
    before writing the adapter) — raw "5" with scale=3 sign=- must resolve to -5000, NOT
    -5 (scale ignored) or -5000000 (scale double-applied)."""
    data = xbrl(fact("Equity", "5", extra='scale="3" sign="-"'))
    result = extract_filing_xml(data, "1", "20231231")

    assert result.observations[0].numeric_value == "-5000"
    assert result.observations[0].scale == 3
    assert result.observations[0].sign == "-"


def test_single_member_context_is_captured_with_dimension_and_member() -> None:
    data = xbrl(
        """<context id="member"><entity><identifier scheme="test">1</identifier>
          <segment><xbrldi:explicitMember dimension="uk:CreditorsDimension">
          uk:WithinOneYear</xbrldi:explicitMember></segment></entity>
          <period><instant>2023-12-31</instant></period></context>""",
        fact("Creditors", "20", context="member"),
    )
    result = extract_filing_xml(data, "1", "20231231")

    assert [(row.dimension, row.member, row.numeric_value) for row in result.observations] == [
        ("CreditorsDimension", "WithinOneYear", "20")
    ]
    assert result.integrity.kept_member == 1


def test_multi_member_context_is_skipped_same_as_ixbrl_path() -> None:
    data = xbrl(
        """<context id="multi"><entity><identifier scheme="test">1</identifier>
          <segment>
            <xbrldi:explicitMember dimension="uk:D1">uk:M1</xbrldi:explicitMember>
            <xbrldi:explicitMember dimension="uk:D2">uk:M2</xbrldi:explicitMember>
          </segment></entity>
          <period><instant>2023-12-31</instant></period></context>""",
        fact("Equity", "1", context="multi"),
    )
    result = extract_filing_xml(data, "1", "20231231")

    assert result.observations == ()
    assert result.integrity.skipped_multimember == 1
    assert result.integrity.closes()


def test_typed_member_context_is_skipped_same_as_ixbrl_path() -> None:
    data = xbrl(
        """<context id="typed"><entity><identifier scheme="test">1</identifier>
          <segment><xbrldi:typedMember dimension="uk:D">
            <uk:domain>1</uk:domain></xbrldi:typedMember></segment></entity>
          <period><instant>2023-12-31</instant></period></context>""",
        fact("Equity", "1", context="typed"),
    )
    result = extract_filing_xml(data, "1", "20231231")

    assert result.observations == ()
    assert result.integrity.skipped_typed == 1
    assert result.integrity.closes()


def test_classify_segments_ignores_typedmembers_own_domain_child_duplicate() -> None:
    """ixbrlparse's own segment list has a documented quirk (BeautifulSoup's findChildren()
    walks all descendants of <segment>, not just direct children): a single typedMember
    dimension produces TWO segment entries — the typedMember tag itself and a second one for
    its own child domain element. Confirmed live against two real filings
    (Prod224_2266_09144549_20230731.html, Prod224_0050_09827898_20171031.html) before
    writing this. Must still classify as ONE typed dimension, not two members."""
    segments = [
        {"tag": "typedMember", "value": "1", "dimension": "core:SomeGroupingDimension"},
        {"tag": "SomeGroupingDimension.domain", "value": "1"},
    ]
    kind, dimension, member = _classify_segments(segments)
    assert kind == ContextKind.TYPED
    assert dimension is None
    assert member is None


def test_dedupe_and_conflict_use_the_same_grouping_logic_as_ixbrl_path() -> None:
    data = xbrl(
        fact("Equity", "100"),
        fact("Equity", "100"),
        fact("CurrentAssets", "50"),
        fact("CurrentAssets", "51"),
    )
    result = extract_filing_xml(data, "1", "20231231")

    assert [(row.concept, row.numeric_value, row.status) for row in result.observations] == [
        ("Equity", "100", "selected"),
        ("CurrentAssets", "50", "conflict_nondimensional"),
        ("CurrentAssets", "51", "conflict_nondimensional"),
    ]
    assert result.integrity.collapsed_duplicate == 1
    assert result.integrity.ambiguous_nondimensional == 2
    assert result.integrity.closes()


def test_company_identifier_is_tagged_same_concept_as_ixbrl_path() -> None:
    data = xbrl(
        '<uk:UKCompaniesHouseRegisteredNumber contextRef="current">'
        "00987654</uk:UKCompaniesHouseRegisteredNumber>",
        fact("Equity", "1"),
    )
    result = extract_filing_xml(data, "00123456", "20231231")

    assert result.company == "00123456"
    assert result.tagged_companies == frozenset({"00987654"})


def test_unrecognisable_content_raises_valueerror_not_ixbrlparseerror() -> None:
    """extract.py's process_archive catches (OSError, RuntimeError, ValueError,
    zipfile.BadZipFile) uniformly for both parsers, without importing ixbrlparse itself —
    ixbrlparse's own IXBRLParseError must be translated to ValueError at this module's
    boundary, not leak through as a type extract.py doesn't know about."""
    with pytest.raises(ValueError, match="ixbrlparse failed"):
        extract_filing_xml(b"not a recognisable document at all", "1", "20231231")


def test_empty_xbrl_root_extracts_cleanly_with_no_facts() -> None:
    """A minimal-but-valid plain-XBRL root with no facts must extract cleanly (zero
    observations, invariant closes) rather than being treated as a failure."""
    result = extract_filing_xml(b"<xbrl/>", "1", "20231231")
    assert result.observations == ()
    assert result.integrity.facts_seen == 0
    assert result.integrity.closes()
