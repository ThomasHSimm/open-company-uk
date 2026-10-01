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


def _filing_with_binding(prefix: str | None, *body: str) -> bytes:
    """Same shape as filing(), but with the inline-XBRL namespace bound the way a real
    filing would declare it: `xmlns:PREFIX="..."` for an explicit prefix, or a bare
    `xmlns="..."` default-namespace declaration when prefix is None. Facts and contexts in
    `body` must already use the matching tag prefix (or none)."""
    contexts = """
      <xbrli:context id="current"><xbrli:period>
        <xbrli:instant>2023-12-31</xbrli:instant></xbrli:period></xbrli:context>
      <xbrli:unit id="gbp"><xbrli:measure>iso4217:GBP</xbrli:measure></xbrli:unit>
    """
    ns_decl = (
        f'xmlns:{prefix}="http://www.xbrl.org/2013/inlineXBRL"'
        if prefix
        else 'xmlns="http://www.xbrl.org/2013/inlineXBRL"'
    )
    return (
        f"<html {ns_decl}>" + contexts + "".join(body) + "</html>"
    ).encode()


def test_ix_prefix_filing_extracts_facts() -> None:
    """Baseline: the conventional `ix:` prefix, confirming no regression."""
    data = _filing_with_binding(
        "ix",
        '<ix:nonFraction name="uk:Equity" contextRef="current" unitRef="gbp">42</ix:nonFraction>',
    )
    result = extract_filing(data, "1", "20231231")
    assert [row.numeric_value for row in result.observations] == ["42"]
    assert result.integrity.zero_fact_ixbrl_filings == 0


def test_other_prefix_filing_extracts_facts() -> None:
    """A filing binding the inline-XBRL namespace to a prefix other than `ix` — e.g.
    `xbrl2` — used to extract zero facts under the old literal-`ix:`-only IX_FACT_RE."""
    data = _filing_with_binding(
        "xbrl2",
        '<xbrl2:nonFraction name="uk:Equity" contextRef="current" '
        'unitRef="gbp">42</xbrl2:nonFraction>',
    )
    result = extract_filing(data, "1", "20231231")
    assert [row.numeric_value for row in result.observations] == ["42"]
    assert result.integrity.zero_fact_ixbrl_filings == 0


def test_default_namespace_filing_extracts_facts() -> None:
    """A filing binding the inline-XBRL namespace as the *default* namespace (no prefix at
    all) — `<nonFraction>`, not `<ix:nonFraction>` — used to extract zero facts under the
    old literal-`ix:`-only IX_FACT_RE."""
    data = _filing_with_binding(
        None,
        '<nonFraction name="uk:Equity" contextRef="current" unitRef="gbp">42</nonFraction>',
    )
    result = extract_filing(data, "1", "20231231")
    assert [row.numeric_value for row in result.observations] == ["42"]
    assert result.integrity.zero_fact_ixbrl_filings == 0


def test_zero_fact_ixbrl_filing_is_flagged_not_treated_as_clean() -> None:
    """A filing that declares the inline-XBRL namespace but has no nonFraction/nonNumeric
    elements at all (e.g. a cover-page-only or malformed filing) must be flagged via
    zero_fact_ixbrl_filings, not silently treated as a clean zero-fact extraction."""
    data = _filing_with_binding("ix", "<p>No facts tagged in this document.</p>")
    result = extract_filing(data, "1", "20231231")
    assert result.observations == ()
    assert result.integrity.facts_seen == 0
    assert result.integrity.zero_fact_ixbrl_filings == 1
    assert result.integrity.closes()  # the flag must not perturb the fact-accounting invariant


def test_non_ixbrl_document_is_not_flagged_as_zero_fact() -> None:
    """A document with no inline-XBRL namespace declared at all (plain XML/HTML) is simply
    not iXBRL — it must not be flagged by zero_fact_ixbrl_filings, which is specifically for
    documents that DO declare the namespace but yield no facts."""
    data = b"<html><body>Not an iXBRL document at all.</body></html>"
    result = extract_filing(data, "1", "20231231")
    assert result.integrity.zero_fact_ixbrl_filings == 0
    assert result.integrity.facts_seen == 0


def test_numdotcomma_format_reads_comma_as_decimal_point() -> None:
    """ixt:numdotcomma: "." is the digit-group separator, "," is the decimal point. The old
    code stripped "," unconditionally regardless of format, silently misreading this as
    123456 (1000x too large) instead of 1234.56 — the real misread this whole audit
    confirmed live against real markup (docs/accounts-parser-check.md §2)."""
    data = filing(fact("Equity", "1.234,56", extra='format="ixt:numdotcomma"'))
    result = extract_filing(data, "1", "20231231")
    assert result.observations[0].numeric_value == "1234.56"
    assert result.integrity.unrecognised_numeric_format == 0


def test_numcomma_format_reads_comma_as_decimal_point() -> None:
    """ixt:numcomma: no digit-group separator at all, "," is the decimal point. The old code
    stripped "," unconditionally, misreading "1234,56" as 123456 instead of 1234.56."""
    data = filing(fact("Equity", "1234,56", extra='format="ixt:numcomma"'))
    result = extract_filing(data, "1", "20231231")
    assert result.observations[0].numeric_value == "1234.56"


def test_numspacecomma_format_reads_comma_as_decimal_point() -> None:
    """ixt:numspacecomma: " " is the digit-group separator, "," is the decimal point. The old
    code stripped both "," and " " unconditionally, misreading "1 234,56" as 123456 instead
    of 1234.56."""
    data = filing(fact("Equity", "1 234,56", extra='format="ixt:numspacecomma"'))
    result = extract_filing(data, "1", "20231231")
    assert result.observations[0].numeric_value == "1234.56"


def test_numcommadecimal_ixt2_prefix_reads_comma_as_decimal_point() -> None:
    """ixt2:numcommadecimal — the TR3/ixt2-namespace name for the same comma-decimal family,
    found live in the archive (282 occurrences). Prefix-agnostic by local name only, the same
    idiom as every other name lookup in this module."""
    data = filing(fact("Equity", "1234,56", extra='format="ixt2:numcommadecimal"'))
    result = extract_filing(data, "1", "20231231")
    assert result.observations[0].numeric_value == "1234.56"


def test_unrecognised_numeric_format_is_null_not_guessed() -> None:
    """A format the Transformation Registry defines but this module doesn't implement (or a
    typo'd/unknown one) must never be guessed at — "never guess" per the brief. The old code
    didn't read the format attribute at all, so it would have unconditionally stripped ","
    and confidently returned "1234" regardless of what the unrecognised format actually
    means — silently wrong rather than honestly null."""
    data = filing(fact("Equity", "1,234", extra='format="ixt:madeupformat"'))
    result = extract_filing(data, "1", "20231231")
    assert result.observations[0].numeric_value is None
    assert result.integrity.unrecognised_numeric_format == 1
    assert result.integrity.closes()  # diagnostic-only counter must not perturb the invariant


def test_nil_like_numeric_format_is_recognised_not_flagged_unrecognised() -> None:
    """zerodash and friends are nil-like, not "unrecognised" — a numeric fact formatted this
    way must resolve to None (deferred to pivot, same as a bare dash) WITHOUT being counted
    as an unrecognised format, so that counter stays a meaningful signal for genuinely
    unhandled formats rather than being inflated by an intentionally-unimplemented-but-known
    family."""
    data = filing(fact("Equity", "-", extra='format="ixt:zerodash"'))
    result = extract_filing(data, "1", "20231231")
    assert result.observations[0].numeric_value is None
    assert result.integrity.unrecognised_numeric_format == 0


def test_dot_decimal_format_unaffected_by_comma_decimal_fix() -> None:
    """Regression safety, not a new-behaviour test (this already worked and must keep
    working): ixt:numdotdecimal is "," as digit-group separator, "." as decimal point —
    exactly the pre-fix unconditional-stripping behaviour, now reached via the explicit
    dot-decimal branch instead of by default."""
    data = filing(fact("Equity", "1,234.56", extra='format="ixt:numdotdecimal"'))
    result = extract_filing(data, "1", "20231231")
    assert result.observations[0].numeric_value == "1234.56"


def test_hyphenated_format_name_is_recognised_same_as_unhyphenated() -> None:
    """Found live in the v2 rebuild's own output: `ixt2:num-dot-decimal` (hyphenated) is the
    exact same Transformation Registry family as `numdotdecimal` (the single most common
    numeric format in the archive, 430M+ occurrences unhyphenated) but was treated as
    unrecognised — silently nulling out a numeric fact that had parsed correctly before the
    comma-decimal fix was written at all. Real markup: a `core:NetAssetsLiabilities` fact,
    raw text "49,386", `format="ixt2:num-dot-decimal"`, from a real 2024 filing. 540
    occurrences confirmed archive-wide (528 `ixt:num-dot-decimal` + 12 `ixt2:num-dot-decimal`,
    from `data/accounts/parser-format-census-total.json`)."""
    data = filing(fact("Equity", "49,386", extra='format="ixt2:num-dot-decimal"'))
    result = extract_filing(data, "1", "20231231")
    assert result.observations[0].numeric_value == "49386"
    assert result.integrity.unrecognised_numeric_format == 0


def test_single_quoted_namespace_declaration_is_recognised() -> None:
    """Real 2013/2014-vintage CH filing software wrote `xmlns:ix='...'` with single quotes
    (found live during the parser-check audit, via a LONG cross-check turning up real rows
    for a filing the census had wrongly called bug-affected). IX_NAMESPACE_RE must match
    both quote styles, the same way core.py's own ATTR_RE already does."""
    data = (
        b"<html xmlns:ix='http://www.xbrl.org/2008/inlineXBRL'>"
        b"<xbrli:context id='current'><xbrli:period>"
        b"<xbrli:instant>2023-12-31</xbrli:instant></xbrli:period></xbrli:context>"
        b"<xbrli:unit id='gbp'><xbrli:measure>iso4217:GBP</xbrli:measure></xbrli:unit>"
        b'<ix:nonFraction name="uk:Equity" contextRef="current" unitRef="gbp">42</ix:nonFraction>'
        b"</html>"
    )
    result = extract_filing(data, "1", "20231231")
    assert [row.numeric_value for row in result.observations] == ["42"]
    assert result.integrity.zero_fact_ixbrl_filings == 0
