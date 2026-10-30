"""Interactions between optional values, composite updates, roots and catalog policies."""

from pathlib import Path

import pytest

from namespec import Catalog, NameSpecError, Resource, load_rules


def codes(exc):
    return [diagnostic.code for diagnostic in exc.value.diagnostics]


@pytest.mark.parametrize("name", ["{x}", "item_{x}.abc"])
def test_location_expands_only_actual_filename_slots(name):
    catalog = Catalog.from_string(
        'spec 1 x = one of "a" resource r { name = "' + name + '" location = "/{{name}}/{name}" }'
    )
    expected = "/{name}/" + name.replace("{x}", "a")
    assert catalog.locate("r", x="a").as_posix() == expected
    assert catalog.parse(expected, "r", source="location").locate().as_posix() == expected


def test_folder_location_allows_an_escaped_filename_literal():
    catalog = Catalog.from_string('spec 1 x = one of "a" resource r { location = "/{{name}}/{x}" }')
    assert catalog.locate("r", x="a").as_posix() == "/{name}/a"


@pytest.mark.parametrize("drive,declared,canonical", [("upper", "c", "C"), ("lower", "C", "c")])
def test_normalization_applies_to_roots_and_literal_locations(drive, declared, canonical):
    catalog = Catalog.from_string(f'''spec 1
        roots {{ win = "{declared}:/jobs" }}
        normalize {{ drive = "{drive}" slashes = "forward" }}
        x = one of "a"
        resource rooted {{ name = "{{x}}" location = "{{root}}/{{name}}" }}
        resource literal {{ location = "{declared}:\\jobs\\{{x}}" }}
    ''')
    expected = f"{canonical}:/jobs/a"
    assert catalog.locate("rooted", root="win", x="a").as_posix() == expected
    assert catalog.locate("rooted", root=f"{declared}:/jobs", x="a").as_posix() == expected
    assert catalog.locate("literal", x="a").as_posix() == expected
    assert catalog.validate(expected, "rooted", source="location").valid
    assert catalog.validate(expected, "literal", source="location").valid
    assert catalog.roots == {"win": f"{canonical}:/jobs"}
    assert catalog.root_name(f"{declared}:/jobs") == "win"


def test_normalized_duplicate_roots_are_rejected():
    with pytest.raises(NameSpecError) as exc:
        Catalog.from_string("""spec 1
            roots { a = "c:/jobs" b = "C:/jobs" }
            normalize { drive = "upper" }
            x = one of "a"
            resource r { location = "{root}/{x}" }
        """)
    assert codes(exc) == ["duplicate_root"]


def test_drive_normalization_does_not_change_unicode_or_offsets():
    catalog = Catalog.from_string("""spec 1
        normalize { drive = "upper" }
        x = one of "a"
        resource r { name = "{x}" }
    """)
    assert catalog.normalize("ß:/a") == "ß:/a"


PAIR = """spec 1
    x = one of "a"
    a = one of "b"
    b = one of "c"
    pair = "{a}_{b}"
    resource r { name = "{x}[_{pair}]" }
"""


def test_samples_treat_optional_composites_as_one_presence_choice():
    catalog = Catalog.from_string(PAIR)
    assert list(catalog.samples("r")) == ["a", "a_b_c"]
    assert list(catalog.samples("r", limit=1)) == ["a"]
    assert list(catalog.samples("r", a="b")) == ["a_b_c"]
    assert list(catalog.samples("r", pair="b_c")) == ["a_b_c"]
    assert list(catalog.samples("r", pair=None)) == ["a"]
    with pytest.raises(NameSpecError) as exc:
        list(catalog.samples("r", a=None, b="c"))
    assert codes(exc) == ["missing_field"]


def test_samples_honor_composite_overrides_and_integer_bounds():
    catalog = Catalog.from_file(Path(__file__).parents[1] / "examples" / "guide.names")
    assert list(catalog.samples("scene", limit=1, Shot="101_120_9999")) == [
        "101_120_9999_comp_v001.nk"
    ]
    bounded = Catalog.from_string(
        'spec 1 n = integer minimum -1 maximum -1 resource r { name = "{n}" }'
    )
    assert list(bounded.samples("r")) == ["-1"]


def test_samples_allow_absent_groups_without_examples_and_zero_limit():
    catalog = Catalog.from_string(PAIR.replace('b = one of "c"', 'b = text matching "[a-z]+"'))
    assert list(catalog.samples("r")) == ["a"]
    assert list(catalog.samples("r", limit=0)) == []
    with pytest.raises(NameSpecError) as exc:
        list(catalog.samples("r", a="b"))
    assert codes(exc) == ["missing_sample"]


def test_repeated_optional_groups_share_sample_presence():
    catalog = Catalog.from_string(
        PAIR.replace('name = "{x}[_{pair}]"', 'name = "{x}[_{a}][_{a}_{b}]"')
    )
    assert list(catalog.samples("r")) == ["a", "a_b_b_c"]


def test_absent_optional_reader_has_a_structured_diagnostic():
    catalog = Catalog.from_string("""spec 1
        x = one of "a"
        ext = one of "txt"
        readers { txt = "text" }
        resource r { name = "{x}[.{ext}]" location = "/tmp/{name}" reader = readers[ext] }
    """)
    assert catalog.parse("a.txt", "r").reader_id == "text"
    for operation in (
        lambda: catalog.parse("a", "r").reader_id,
        lambda: catalog.parse("a", "r").read(),
    ):
        with pytest.raises(NameSpecError) as exc:
            operation()
        assert codes(exc) == ["missing_reader"]
        assert exc.value.diagnostics[0].field == "ext"


def test_replace_recomputes_nested_composites_and_preserves_bound_class():
    catalog = Catalog.from_file(Path(__file__).parents[1] / "examples" / "guide.names")

    @catalog.resource("scene")
    class Scene(Resource):
        pass

    original = catalog.parse("101_120_0040_comp_v003.nk", "scene")
    changed = original.replace(shotnum="0041")
    assert type(changed) is Scene
    assert changed.name == "101_120_0041_comp_v003.nk"
    assert changed.fields["Shot"] == "101_120_0041"
    assert changed.fields["Sequence"] == "101_120"
    assert original.name == "101_120_0040_comp_v003.nk"
    assert original.replace(Shot="102_125_0042").fields["Episode"] == "102"
    assert original.replace(Sequence="102_125").fields["Shot"] == "102_125_0040"
    with pytest.raises(NameSpecError) as exc:
        original.replace(Shot="101_120_0041", shotnum="0042")
    assert "conflicting_field" in codes(exc)
    with pytest.raises(NameSpecError) as exc:
        original.replace(shootnum="0041")
    assert codes(exc) == ["unknown_field"]


def test_replace_removes_optional_composites_and_keeps_location_context():
    catalog = Catalog.from_string(PAIR + 'resource located { location = "/{x}[_{pair}]" }')
    assert catalog.parse("a_b_c", "r").replace(pair=None).name == "a"
    located = catalog.parse("/a_b_c", "located", source="location")
    assert located.replace(pair=None).locate().as_posix() == "/a"
    assert located.locate().as_posix() == "/a_b_c"


def test_strict_roundtrip_is_opt_in_and_replace_always_preserves_requested_values():
    source = """spec 1
        a = text matching "[a-z_]+"
        b = text matching "[a-z_]+"
        resource r { name = "{a}_{b}" }
    """
    catalog = Catalog.from_string(source)
    assert catalog.format("r", a="x", b="y_z") == "x_y_z"
    strict = Catalog.from_string(source, strict=True)
    with pytest.raises(NameSpecError) as exc:
        strict.format("r", a="x", b="y_z")
    assert "non_roundtripping_value" in codes(exc)
    original = catalog.parse("x_y", "r")
    with pytest.raises(NameSpecError) as exc:
        original.replace(b="y_z")
    assert "non_roundtripping_value" in codes(exc)


def test_loaders_share_the_same_cache_for_equivalent_calls(tmp_path, monkeypatch):
    path = tmp_path / "rules.names"
    path.write_text(PAIR, encoding="utf-8")
    monkeypatch.setenv("NAMESPEC_RULES", str(path))
    load_rules.cache_clear()
    try:
        catalog = load_rules()
        assert Catalog.from_env() is catalog
        assert load_rules(variable="NAMESPEC_RULES", default=None, strict=False) is catalog
        assert load_rules(strict=True) is not catalog
        assert Catalog.from_env(strict=True) is load_rules(strict=True)
    finally:
        load_rules.cache_clear()
