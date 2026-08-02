from ukcompany.validate import normalise_company_number, validate_input


def test_ok_8_digits():
    r = normalise_company_number("01234567")
    assert r.status == "ok" and r.number == "01234567"


def test_excel_stripped_leading_zero():
    r = normalise_company_number("1234567")
    assert r.status == "fixed" and r.number == "01234567"
    assert "zero-padded" in r.note


def test_excel_float_damage():
    r = normalise_company_number("1234567.0")
    assert r.status == "fixed" and r.number == "01234567"


def test_integer_input():
    r = normalise_company_number(1234567)
    assert r.status == "fixed" and r.number == "01234567"


def test_prefixed_ok():
    r = normalise_company_number("SC345678")
    assert r.status == "ok" and r.number == "SC345678"


def test_prefixed_lowercase_and_padding():
    r = normalise_company_number("sc1234")
    assert r.status == "fixed" and r.number == "SC001234"


def test_unknown_prefix_accepted_with_warning():
    r = normalise_company_number("ZZ123456")
    assert r.valid and "unrecognised prefix" in r.note


def test_invalid_garbage():
    for bad in ["", None, "123456789", "1B345678", "SC12345X", "hello"]:
        assert normalise_company_number(bad).status == "invalid", bad


def test_validate_input_report_and_dedup():
    report = validate_input(["01234567", "1234567", "nope", "SC345678"])
    assert len(report.ok) == 2 and len(report.fixed) == 1 and len(report.invalid) == 1
    # "1234567" normalises to the same number as "01234567" -> duplicate
    assert report.duplicates == ["01234567"]
    assert report.numbers == ["01234567", "SC345678"]


def test_report_summary_names_the_damage():
    report = validate_input(["1234567"])
    assert "FIXED" in report.summary()
