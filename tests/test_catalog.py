from __future__ import annotations

import json
from pathlib import Path

import pytest

from namespec import Catalog, NameSpecError
from namespec.cli import main

EXAMPLE = Path(__file__).parents[1] / "examples" / "assets.names"


def codes(exc):
    return [diagnostic.code for diagnostic in exc.value.diagnostics]


def test_context_cannot_overwrite_parsed_metadata(catalog, valid_case):
    resource = catalog.parse(valid_case.input)
    with pytest.raises(NameSpecError) as exc:
        resource.locate(job="x", asset_name="Chair")
    assert codes(exc) == ["context_conflict"]


@pytest.mark.parametrize("version", [True, "4", 4.0])
def test_generation_rejects_wrong_types(catalog, valid_case, version):
    with pytest.raises(NameSpecError) as exc:
        catalog.format(valid_case.resource, **{**valid_case.fields, "version": version})
    assert codes(exc) == ["invalid_type"]


def test_missing_generation_fields_are_aggregated(catalog, valid_case):
    with pytest.raises(NameSpecError) as exc:
        catalog.format(valid_case.resource, asset_name=valid_case.fields["asset_name"])
    assert {d.field for d in exc.value.diagnostics} == {"lod", "version", "filetype"}


def test_identification_keeps_ambiguity_visible():
    catalog = Catalog.from_string("""spec 1
        resource first { name = "{item}" }
        resource second { name = "{item}" }
        item = text matching "[a-z]+"
    """)
    result = catalog.inspect("donut")
    assert result.status == "ambiguous"
    assert {match.resource for match in result.matches} == {"first", "second"}
    with pytest.raises(NameSpecError) as exc:
        catalog.parse("donut")
    assert codes(exc) == ["ambiguous_resource"]
    assert catalog.parse("donut", "first").kind == "first"


def test_schema_examples_and_generated_round_trips(catalog, valid_case):
    assert not catalog.check_examples()
    samples = list(catalog.samples(valid_case.resource, limit=100))
    assert len(samples) == 36
    for name in samples:
        resource = catalog.parse(name)
        assert resource.name == name
        location = resource.locate(**valid_case.context)
        assert catalog.parse(location, source="location").name == name


def test_failed_expected_examples_are_reported():
    source = EXAMPLE.read_text(encoding="utf-8").replace("version = 4\n", "version = 9\n")
    failures = Catalog.from_string(source).check_examples()
    assert len(failures) == 1
    assert failures[0].code == "example_failed"


def test_export_is_json_serializable(catalog):
    model = json.loads(json.dumps(catalog.definition.to_dict()))
    assert model["spec_version"] == 1
    assert model["fields"]["version"]["kind"] == "integer"


def test_reader_is_explicit_and_uses_supplied_metadata(tmp_path):
    directory = tmp_path.as_posix()
    source = """spec 1
        resource note {
            name = "{title}.{ext}"
            location = "ROOT/{name}"
            reader = readers[ext]
        }
        title = text matching "[a-z]+"
        ext = one of "txt"
        readers { txt = "text" }
    """.replace("ROOT", directory)
    catalog = Catalog.from_string(source)
    resource = catalog.parse("hello.txt")
    with pytest.raises(NameSpecError) as exc:
        resource.read()
    assert codes(exc) == ["unavailable_reader"]
    calls = []

    def read_text(path):
        calls.append(path)
        return path.read_text(encoding="utf-8")

    catalog.register_reader("text", read_text)
    assert not calls
    (tmp_path / "hello.txt").write_text("Hello", encoding="utf-8")
    assert resource.read() == "Hello"
    assert calls == [tmp_path / "hello.txt"]


@pytest.mark.parametrize(
    "source,code",
    [
        ("spec 2", "unsupported_spec"),
        ("spec 1", "missing_resource"),
        ('spec 1 resource bad { name = "{missing}" }', "unknown_field"),
        ('spec 1 resource a { name = "{x}{x}" } x = one of "a"', "ambiguous_template"),
        ('spec 1 resource a { name = "{x}" } x = text matching "["', "invalid_pattern"),
        ('spec 1 resource a { name = "{x}" } x = text matching ".*"', "empty_field"),
        (
            'spec 1 resource a { name = "{x}" } x = one of "a" x = one of "b"',
            "duplicate_definition",
        ),
        ('spec 1 resource a { name = "{x}" } x = one of "a", "a"', "duplicate_choice"),
        ('spec 1 resource a { name = "{x}" } x = integer minimum -1', "invalid_integer"),
        ('spec 1 resource a { name = "{x}" } x = text matching "a" examples "b"', "invalid_sample"),
        (
            'spec 1 resource a { name = "{x}" reader = readers[x] } x = one of "abc"',
            "missing_reader_mapping",
        ),
        (
            'spec 1 resource a { name = "{x}" location = "/jobs/{job}" } '
            'x = one of "a" job = one of "b"',
            "incomplete_location",
        ),
    ],
)
def test_definition_errors_are_actionable(source, code):
    with pytest.raises(NameSpecError) as exc:
        Catalog.from_string(source)
    assert codes(exc) == [code]


def test_reserved_delimiter_is_rejected_when_generating():
    catalog = Catalog.from_string("""spec 1
        resource item { name = "{part}_{ext}" }
        part = text matching "[a-z_]+"
        ext = one of "abc"
    """)
    with pytest.raises(NameSpecError) as exc:
        catalog.format("item", part="bad_name", ext="abc")
    assert codes(exc) == ["reserved_separator"]


def test_cli_json_and_exit_codes(capsys, valid_case, invalid_case):
    assert main([str(valid_case.schema), "inspect", valid_case.input]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "valid"
    assert main([str(invalid_case.schema), "inspect", invalid_case.input]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "invalid"
    assert main([str(EXAMPLE), "test"]) == 0
    assert json.loads(capsys.readouterr().out)["passed"]


def test_location_requires_context(catalog, valid_case):
    resource = catalog.parse(valid_case.input)
    with pytest.raises(NameSpecError) as exc:
        resource.locate()
    assert codes(exc) == ["missing_field"]
    assert exc.value.diagnostics[0].field == "job"
