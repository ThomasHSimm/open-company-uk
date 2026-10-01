from scripts.panel_check import distinct_periods, extract_filing


def test_extracts_each_facts_period_end_and_densifies_filing() -> None:
    data = b"""
    <html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL">
      <xbrli:context id="cfwd_30_07_2025">
        <xbrli:period><xbrli:instant>2025-07-30</xbrli:instant></xbrli:period>
      </xbrli:context>
      <xbrli:context id="cfwd_15_11_2024">
        <xbrli:period><xbrli:instant>2024-11-15</xbrli:instant></xbrli:period>
      </xbrli:context>
      <ix:nonFraction name="ns5:CashBankOnHand" contextRef="cfwd_30_07_2025"
          unitRef="GBP" decimals="0" scale="3">324,550</ix:nonFraction>
      <ix:nonFraction name="ns5:Equity" contextRef="cfwd_15_11_2024"
          unitRef="GBP" decimals="0">100</ix:nonFraction>
    </html>
    """

    filing = extract_filing(data, "00000295", "20250730")

    assert distinct_periods(filing) == {"2025-07-30", "2024-11-15"}
    assert filing.facts[0].numeric_value == "324550000"
    assert filing.bad_period_refs == 0


def test_prefers_non_dimensional_total_over_components() -> None:
    data = b"""
    <html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL">
      <xbrli:context id="component"><xbrli:entity><xbrli:segment>
        <xbrldi:explicitMember dimension="d">member</xbrldi:explicitMember>
      </xbrli:segment></xbrli:entity><xbrli:period>
        <xbrli:instant>2023-12-31</xbrli:instant></xbrli:period></xbrli:context>
      <xbrli:context id="total"><xbrli:period>
        <xbrli:instant>2023-12-31</xbrli:instant></xbrli:period></xbrli:context>
      <ix:nonFraction name="uk:Equity" contextRef="component">40</ix:nonFraction>
      <ix:nonFraction name="uk:Equity" contextRef="total">100</ix:nonFraction>
    </html>
    """

    filing = extract_filing(data, "1", "20240101")

    assert [(fact.concept, fact.raw_value) for fact in filing.facts] == [("Equity", "100")]
