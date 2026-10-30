"""Automatic source selection follows template matches, including relative locations."""

from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from namespec import Catalog, NameSpecError, Resource

SOURCE = """spec 1
roots { linux = "/jobs" windows = "J:/jobs" }
normalize { drive = "upper" slashes = "forward" }
asset = text matching "[A-Z][a-z]+"
version = integer minimum 1 padded to 3 digits
ext = one of "abc", "usd"
resource model {
    name = "{asset}_v{version}.{ext}"
    location = "{root}/assets/{asset}/{name}"
}
resource relative_folder { location = "assets-{asset}" }
resource path_shaped_name { name = "names/{asset}" }
"""


@pytest.fixture
def catalog():
    return Catalog.from_string(SOURCE)


def codes(diagnostics):
    return [item.code for item in diagnostics]


@pytest.mark.parametrize(
    "text,kind,source",
    [
        ("Donut_v004.abc", "model", "name"),
        ("/jobs/assets/Donut/Donut_v004.abc", "model", "location"),
        (r"j:\jobs\assets\Donut\Donut_v004.abc", "model", "location"),
        ("assets-Donut", "relative_folder", "location"),
        ("names/Donut", "path_shaped_name", "name"),
        (Path("Donut_v004.abc"), "model", "name"),
        (PurePosixPath("/jobs/assets/Donut/Donut_v004.abc"), "model", "location"),
        (PureWindowsPath(r"J:\jobs\assets\Donut\Donut_v004.abc"), "model", "location"),
    ],
)
def test_auto_source_uses_templates_for_names_paths_and_path_objects(catalog, text, kind, source):
    parsed = catalog.parse(text)
    assert parsed.kind == kind
    assert parsed.source == source
    assert parsed.fields["asset"] == "Donut"
    selected = catalog.parse(text, kind)
    assert selected.fields == parsed.fields
    assert selected.source == source
    validated = catalog.validate(text, kind)
    assert validated.valid and validated.source == source
    inspected = catalog.inspect(text)
    assert inspected.status == "valid"
    assert inspected.matches == (validated,)


def test_auto_location_keeps_normalized_input_and_offsets(catalog):
    text = r"j:\jobs\assets\Donut\Donut_v004.exe"
    result = catalog.validate(text, "model")
    assert result.source == "location"
    assert result.input == "J:/jobs/assets/Donut/Donut_v004.exe"
    assert codes(result.diagnostics) == ["invalid_field"]
    diagnostic = result.diagnostics[0]
    assert diagnostic.field == "ext"
    assert text[slice(*diagnostic.span)] == "exe"
    assert result.fields["version"] == 4
    with pytest.raises(NameSpecError) as exc:
        catalog.parse(text, "model")
    assert exc.value.diagnostics == list(result.diagnostics)


def test_auto_selected_invalid_name_retains_field_diagnostics(catalog):
    result = catalog.validate("Donut_v4.abc", "model")
    assert result.source == "name"
    assert codes(result.diagnostics) == ["noncanonical_field"]
    assert result.diagnostics[0].field == "version"
    assert result.fields == {"asset": "Donut", "ext": "abc"}


def test_inspection_exposes_invalid_candidates_with_actual_sources(catalog):
    text = "/jobs/assets/Chair/Donut_v004.abc"
    result = catalog.validate(text, "model")
    inspection = catalog.inspect(text)
    assert inspection.status == "invalid"
    assert result in inspection.candidates
    assert result.source == "location"
    assert codes(result.diagnostics) == ["conflicting_field"]
    with pytest.raises(NameSpecError) as exc:
        catalog.parse(text)
    assert codes(exc.value.diagnostics) == ["no_match"]


def test_identical_name_and_location_readings_collapse_to_location():
    catalog = Catalog.from_string("""spec 1
        x = one of "a"
        resource r { name = "{x}" location = "{name}" }
    """)
    inspection = catalog.inspect("a")
    assert inspection.status == "valid"
    assert len(inspection.matches) == 1
    assert inspection.matches[0].source == "location"
    assert catalog.validate("a", "r").source == "location"
    assert catalog.parse("a").source == "location"
    assert catalog.parse("a", source="name").source == "name"


SWAPPED = """spec 1
a = text matching "[a-z]+"
b = text matching "[a-z]+"
resource pair { name = "{a}_{b}" location = "{b}_{a}" }
"""


def test_distinct_same_resource_readings_are_source_ambiguity():
    catalog = Catalog.from_string(SWAPPED)
    inspection = catalog.inspect("one_two")
    assert inspection.status == "ambiguous"
    assert [result.source for result in inspection.matches] == ["name", "location"]
    assert [result.fields for result in inspection.matches] == [
        {"a": "one", "b": "two"},
        {"a": "two", "b": "one"},
    ]
    result = catalog.validate("one_two", "pair")
    assert not result.valid and result.source == "auto" and result.fields == {}
    assert codes(result.diagnostics) == ["ambiguous_source"]
    assert result.diagnostics[0].actual == [
        {"source": match.source, "fields": match.fields} for match in inspection.matches
    ]
    for resource in (None, "pair"):
        with pytest.raises(NameSpecError) as exc:
            catalog.parse("one_two", resource)
        assert codes(exc.value.diagnostics) == ["ambiguous_source"]
    assert catalog.parse("one_two", source="name").fields["a"] == "one"
    assert catalog.parse("one_two", source="location").fields["a"] == "two"
    assert catalog.inspect("one_one").status == "valid"
    assert catalog.parse("one_one").source == "location"


def test_different_resources_remain_ambiguous_even_when_their_fields_agree():
    catalog = Catalog.from_string(SWAPPED + 'resource folder { location = "{a}_{b}" }')
    with pytest.raises(NameSpecError) as exc:
        catalog.parse("one_one")
    assert codes(exc.value.diagnostics) == ["ambiguous_resource"]
    assert exc.value.diagnostics[0].actual == ["pair", "folder"]
    with pytest.raises(NameSpecError) as exc:
        catalog.parse("one_two")
    assert codes(exc.value.diagnostics) == ["ambiguous_resource"]
    assert exc.value.diagnostics[0].actual == ["pair", "folder"]
    assert catalog.parse("one_two", "folder").source == "location"


def test_auto_invalid_source_candidates_keep_both_diagnostic_sets():
    catalog = Catalog.from_string("""spec 1
        x = one of "a"
        resource r { name = "{x}" location = "{name}" }
    """)
    result = catalog.validate("b", "r")
    assert not result.valid and result.source == "auto"
    assert codes(result.diagnostics) == ["invalid_field", "invalid_field"]
    assert [item.message.split(":", 1)[0] for item in result.diagnostics] == ["name", "location"]
    assert all(item.field == "x" and item.actual == "b" for item in result.diagnostics)


def test_auto_structural_failure_is_one_diagnostic_without_a_guessed_source(catalog):
    result = catalog.validate("not a model", "model")
    assert result.source == "auto" and result.fields == {}
    assert codes(result.diagnostics) == ["pattern_mismatch"]
    assert set(result.diagnostics[0].expected) == {"name", "location"}


def test_explicit_source_overrides_auto_and_preserves_missing_template_errors(catalog):
    assert not catalog.validate("Donut_v004.abc", "model", source="location").valid
    assert not catalog.validate("/jobs/assets/Donut/Donut_v004.abc", "model", source="name").valid
    with pytest.raises(NameSpecError) as exc:
        catalog.validate("assets-Donut", "relative_folder", source="name")
    assert codes(exc.value.diagnostics) == ["missing_name"]
    with pytest.raises(NameSpecError) as exc:
        catalog.validate("names/Donut", "path_shaped_name", source="location")
    assert codes(exc.value.diagnostics) == ["missing_location"]
    assert catalog.inspect("assets-Donut", source="name").status == "invalid"


@pytest.mark.parametrize("operation", ["parse", "validate", "inspect"])
def test_bad_source_is_an_operation_error(catalog, operation):
    args = ("Donut_v004.abc", "model") if operation == "validate" else ("Donut_v004.abc",)
    with pytest.raises(NameSpecError) as exc:
        getattr(catalog, operation)(*args, source="guess")
    assert codes(exc.value.diagnostics) == ["invalid_source"]


def test_auto_keeps_bound_class_and_source_for_further_operations(catalog):
    @catalog.resource("model")
    class Model(Resource):
        pass

    parsed = catalog.parse("/jobs/assets/Donut/Donut_v004.abc")
    assert type(parsed) is Model and parsed.source == "location"
    changed = parsed.replace(version=5)
    assert type(changed) is Model and changed.source == "location"
    assert changed.locate() == Path("/jobs/assets/Donut/Donut_v005.abc")


def test_inline_examples_keep_their_explicit_source():
    catalog = Catalog.from_string(
        SWAPPED
        + """
        example pair { input = "one_two" expect { a = "one" b = "two" } }
        example pair { location = "one_two" expect { a = "two" b = "one" } }
    """
    )
    assert catalog.check_examples() == []


def test_auto_source_accepts_string_pathlike_objects(catalog):
    class StudioPath:
        def __fspath__(self):
            return "assets-Donut"

    assert catalog.parse(StudioPath()).source == "location"
    assert catalog.validate(StudioPath(), "relative_folder").valid


def test_auto_source_preserves_filesystem_diagnostics():
    pytest.importorskip("pathvalidate")
    catalog = Catalog.from_string(
        """spec 1 stem = text matching "[A-Z]+"
        resource r { name = "{stem}.txt" location = "files/{name}" }
        """,
        filesystem="portable",
    )
    result = catalog.validate("CON.txt", "r")
    assert result.source == "name" and codes(result.diagnostics) == ["unsafe_path"]
    result = catalog.validate("..", "r")
    assert result.source == "auto"
    assert codes(result.diagnostics) == ["pattern_mismatch", "unsafe_path"]
