"""The CSV is the expected answer; this test exercises every row without inventing answers."""

from collections import Counter

import pytest

from namespec import NameSpecError


def test_name_case(name_case, case_catalog):
    case = name_case
    catalog = case_catalog
    result = catalog.validate(case.input, case.resource, source=case.source)
    assert result.valid == case.valid, case.notes
    assert result.fields == case.fields, case.notes
    assert {key: type(value) for key, value in result.fields.items()} == {
        key: type(value) for key, value in case.fields.items()
    }
    assert Counter((d.code, d.field) for d in result.diagnostics) == Counter(case.diagnostics)
    for diagnostic in result.diagnostics:
        if diagnostic.span is not None:
            assert case.input[slice(*diagnostic.span)] == diagnostic.actual

    inspection = catalog.inspect(case.input, source=case.source)
    if not case.valid:
        assert not any(match.resource == case.resource for match in inspection.matches)
        if all(code != "pattern_mismatch" for code, _ in case.diagnostics):
            assert result in inspection.candidates
        return

    assert {match.resource for match in inspection.matches} == set(case.matches)
    assert inspection.status == ("valid" if len(case.matches) == 1 else "ambiguous")
    if len(case.matches) == 1:
        assert catalog.parse(case.input, source=case.source).kind == case.resource
    else:
        with pytest.raises(NameSpecError) as exc:
            catalog.parse(case.input, source=case.source)
        assert [d.code for d in exc.value.diagnostics] == ["ambiguous_resource"]
    resource = catalog.parse(case.input, case.resource, source=case.source)
    assert resource.kind == case.resource
    assert resource.fields == case.fields
    if case.source == "name":
        assert resource.name == case.input
    else:
        assert resource.locate() == case.input
    if case.reader:
        assert resource.reader_id == case.reader
    if case.location:
        assert resource.locate(**case.context) == case.location
        located = catalog.parse(case.location, case.resource, source="location")
        assert located.fields == {**case.context, **case.fields}
