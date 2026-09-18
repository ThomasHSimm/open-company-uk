from ukcompany.accounts.core import ContextKind, extract_contexts, extract_filing


def filing(*body: str) -> bytes:
    contexts = """
      <xbrli:context id="current"><xbrli:period>
        <xbrli:instant>2023-12-31</xbrli:instant></xbrli:period></xbrli:context>
      <xbrli:context id="prior"><xbrli:period>
        <xbrli:instant>2022-12-31</xbrli:instant></xbrli:period></xbrli:context>
      <xbrli:unit id="gbp"><xbrli:measure>iso4217:GBP</xbrli:measure></xbrli:unit>
      <xbrli:unit id="eur"><xbrli:measure>iso4217:EUR</xbrli:measure></xbrli:unit>
      <xbrli:unit id="people"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>
    """
    return ("<html>" + contexts + "".join(body) + "</html>").encode()


def fact(
    concept: str,
    value: str,
    *,
    context: str = "current",
    unit: str = "gbp",
    extra: str = "",
) -> str:
    return (
        f'<ix:nonFraction name="uk:{concept}" contextRef="{context}" '
        f'unitRef="{unit}" {extra}>{value}</ix:nonFraction>'
    )


def test_clean_total_scale_sign_currency_and_current_period() -> None:
    result = extract_filing(
        filing(
            fact("Equity", "1", extra='scale="3"'),
            fact("CashBankOnHand", "1,234", extra='sign="-"'),
            fact("Debtors", "(1,234)", context="prior"),
        ),
        "00123456",
        "20231231",
    )

    assert [row.numeric_value for row in result.observations] == ["1000", "-1234", "-1234"]
    assert [row.is_current for row in result.observations] == [True, True, False]
    assert result.observations[1].sign == "-"
    assert {row.currency for row in result.observations} == {"GBP"}
    assert result.integrity.kept_total == 3
    assert result.integrity.closes()


def test_all_scope_non_target_text_and_restricted_numeric_scope() -> None:
    data = filing(
        fact("CustomMetric", "7"),
        '<ix:nonNumeric name="uk:EntityTradingStatus" contextRef="current">'
        "Dormant company</ix:nonNumeric>",
        '<ix:nonNumeric name="uk:ReportingPeriodEndDate" contextRef="current">'
        "2023-12-31</ix:nonNumeric>",
        fact("Equity", "10"),
    )

    all_facts = extract_filing(data, "1", "20231231")
    restricted = extract_filing(
        data,
        "1",
        "20231231",
        scope=["CustomMetric", "EntityTradingStatus"],
        kinds="numeric-only",
    )

    assert [
        (row.concept, row.fact_kind, row.raw_value, row.numeric_value, row.status)
        for row in all_facts.observations
    ] == [
        ("CustomMetric", "numeric", "7", "7", "selected"),
        ("EntityTradingStatus", "non-numeric", "Dormant company", None, "selected"),
        ("ReportingPeriodEndDate", "non-numeric", "2023-12-31", None, "selected"),
        ("Equity", "numeric", "10", "10", "selected"),
    ]
    assert [(row.concept, row.numeric_value) for row in restricted.observations] == [
        ("CustomMetric", "7")
    ]
    assert all_facts.integrity.facts_seen == 4
    assert restricted.integrity.facts_seen == 1
    assert all_facts.integrity.closes()
    assert restricted.integrity.closes()


def test_total_conflict_and_agreeing_duplicate_have_separate_buckets() -> None:
    result = extract_filing(
        filing(
            fact("Equity", "100"),
            fact("Equity", "101"),
            fact("CurrentAssets", "50"),
            fact("CurrentAssets", "50"),
        ),
        "1",
        "20231231",
    )

    assert [(row.concept, row.numeric_value, row.status) for row in result.observations] == [
        ("Equity", "100", "conflict_nondimensional"),
        ("Equity", "101", "conflict_nondimensional"),
        ("CurrentAssets", "50", "selected"),
    ]
    assert result.integrity.ambiguous_nondimensional == 2
    assert result.integrity.kept_total == 1
    assert result.integrity.collapsed_duplicate == 1
    assert result.integrity.closes()


def test_single_members_uniform_capture_dedupe_and_conflict() -> None:
    data = filing(
        """<xbrli:context id="within"><xbrli:entity><xbrli:segment>
          <xbrldi:explicitMember dimension="uk:CreditorsDimension">
            uk:WithinOneYear
          </xbrldi:explicitMember></xbrli:segment></xbrli:entity>
          <xbrli:period><xbrli:instant>2023-12-31</xbrli:instant></xbrli:period>
        </xbrli:context>""",
        """<xbrli:context id="after"><xbrli:entity><xbrli:segment>
          <xbrldi:explicitMember dimension="uk:CreditorsDimension">
            uk:AfterOneYear
          </xbrldi:explicitMember></xbrli:segment></xbrli:entity>
          <xbrli:period><xbrli:instant>2023-12-31</xbrli:instant></xbrli:period>
        </xbrli:context>""",
        """<xbrli:context id="debtor"><xbrli:scenario>
          <xbrldi:explicitMember dimension="uk:DebtorsDimension">uk:TradeDebtors
          </xbrldi:explicitMember></xbrli:scenario><xbrli:period>
          <xbrli:instant>2023-12-31</xbrli:instant></xbrli:period></xbrli:context>""",
        fact("Creditors", "20", context="within"),
        fact("Creditors", "30", context="after"),
        fact("Creditors", "20", context="within"),
        fact("Creditors", "31", context="after"),
        fact("Debtors", "9", context="debtor"),
    )

    result = extract_filing(data, "1", "20231231")

    assert [
        (row.concept, row.member, row.numeric_value, row.status)
        for row in result.observations
    ] == [
        ("Creditors", "WithinOneYear", "20", "selected"),
        ("Creditors", "AfterOneYear", "30", "conflict_member"),
        ("Creditors", "AfterOneYear", "31", "conflict_member"),
        ("Debtors", "TradeDebtors", "9", "selected"),
    ]
    assert result.integrity.kept_member == 2
    assert result.integrity.collapsed_duplicate == 1
    assert result.integrity.member_value_conflict == 2
    assert result.integrity.closes()


def test_multi_typed_bad_context_and_non_gbp_accounting_close() -> None:
    data = filing(
        """<xbrli:context id="multi"><xbrli:entity><xbrli:segment>
          <xbrldi:explicitMember dimension="uk:D1">uk:M1</xbrldi:explicitMember>
          <xbrldi:explicitMember dimension="uk:D2">uk:M2</xbrldi:explicitMember>
          </xbrli:segment></xbrli:entity><xbrli:period>
          <xbrli:instant>2023-12-31</xbrli:instant></xbrli:period></xbrli:context>""",
        """<xbrli:context id="typed"><xbrli:scenario>
          <xbrldi:typedMember dimension="uk:D"><uk:value>X</uk:value></xbrldi:typedMember>
          </xbrli:scenario><xbrli:period><xbrli:instant>2023-12-31</xbrli:instant>
          </xbrli:period></xbrli:context>""",
        fact("Equity", "1", context="multi"),
        fact("Equity", "2", context="typed"),
        fact("Equity", "3", context="missing"),
        fact("Equity", "4", unit="eur"),
        fact("AverageNumberEmployeesDuringPeriod", "5", unit="people"),
    )

    result = extract_filing(data, "00000001", "20231231")

    assert result.integrity.skipped_multimember == 1
    assert result.integrity.skipped_typed == 1
    assert result.integrity.bad_period_refs == 1
    assert result.integrity.non_gbp_facts == 1
    assert result.integrity.closes()
    assert [row.currency for row in result.observations] == ["EUR", None]
    assert [row.unit for row in result.observations] == ["EUR", "pure"]


def test_context_local_names_and_company_identifier_preserve_leading_zeros() -> None:
    data = filing(
        """<xbrli:context id="member"><xbrli:scenario>
          <xbrldi:explicitMember dimension="uk:ClassesDimension">uk:OrdinarySharesMember
          </xbrldi:explicitMember></xbrli:scenario><xbrli:period>
          <xbrli:instant>2023-12-31</xbrli:instant></xbrli:period></xbrli:context>""",
        fact("Equity", "1", context="member"),
        '<ix:nonNumeric name="uk:UKCompaniesHouseRegisteredNumber" '
        'contextRef="current">00987654</ix:nonNumeric>',
    )

    contexts, invalid = extract_contexts(data)
    result = extract_filing(data, "00123456", "20231231")

    assert invalid == 0
    assert contexts["member"].kind == ContextKind.SINGLE_MEMBER
    assert contexts["member"].dimension == "ClassesDimension"
    assert contexts["member"].member == "OrdinarySharesMember"
    assert result.company == "00123456"
    assert result.tagged_companies == frozenset({"00987654"})


def test_legacy_dimensional_fallback_is_audit_only() -> None:
    data = filing(
        """<xbrli:context id="member"><xbrli:scenario>
          <xbrldi:explicitMember dimension="uk:CreditorsDimension">uk:WithinOneYear
          </xbrldi:explicitMember></xbrli:scenario><xbrli:period>
          <xbrli:instant>2023-12-31</xbrli:instant></xbrli:period></xbrli:context>""",
        fact("Creditors", "12", context="member"),
    )

    result = extract_filing(data, "1", "20231231")

    assert [(row.concept, row.numeric_value) for row in result.legacy_fallbacks] == [
        ("Creditors", "12")
    ]
    assert [(row.dimension, row.member) for row in result.observations] == [
        ("CreditorsDimension", "WithinOneYear")
    ]


def test_self_closing_nil_fact_is_seen_and_does_not_consume_next_fact() -> None:
    data = filing(
        '<ix:nonFraction name="uk:Equity" contextRef="current" unitRef="gbp" xsi:nil="true"/>',
        fact("CashBankOnHand", "7"),
    )

    result = extract_filing(data, "1", "20231231")

    assert [(row.concept, row.numeric_value) for row in result.observations] == [
        ("Equity", None),
        ("CashBankOnHand", "7"),
    ]
    assert result.integrity.facts_seen == 2
    assert result.integrity.kept_total == 2
    assert result.integrity.closes()
