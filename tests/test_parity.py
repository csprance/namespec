"""What a plain regex matcher allows, namespec allows too: free patterns, paths, single fields."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from namespec import Catalog, NameSpecError, load_rules

SOURCE = """spec 1
roots { mac = "/Volumes" win = "C:/projects" }
// Regex style: one flat pattern that contains the template's own underscores.
FlatShot = text matching "[A-Za-z0-9]+_[A-Za-z0-9]+_[A-Za-z0-9]+" examples "405_003_0400"
// namespec style: the same shape as parts, so a wrong part is reported by name.
Episode  = text matching "[A-Za-z0-9]+" examples "405"
seqnum   = text matching "[0-9]+" examples "003"
shotnum  = text matching "[0-9]+" examples "0400"
Sequence = "{Episode}_{seqnum}"
Shot     = "{Sequence}_{shotnum}"
label    = text matching "[A-Za-z0-9_]+" examples "my_label"
Task     = one of "comp", "anim"
version  = integer minimum 0 padded to 3 digits
ext      = text matching "[a-z]+" examples "nk"

resource flat     { name = "{FlatShot}_{Task}_v{version}.{ext}" }
resource scene    { name = "{Shot}_{Task}_v{version}.{ext}" location = "{root}/{Shot}/{name}" }
resource labelled { name = "{label}_{Task}.{ext}" }
"""


def codes(diagnostics):
    return [(item.code, item.field) for item in diagnostics]


@pytest.fixture(scope="module")
def catalog():
    return Catalog.from_string(SOURCE)


def test_a_field_may_contain_the_templates_punctuation_when_its_rule_allows_it(catalog):
    flat = catalog.parse("405_003_0400_comp_v006.nk", "flat")
    assert flat.fields == {"FlatShot": "405_003_0400", "Task": "comp", "version": 6, "ext": "nk"}
    assert flat.name == "405_003_0400_comp_v006.nk"
    labelled = catalog.parse("my_label_x_comp.nk", "labelled")
    assert labelled.fields == {"label": "my_label_x", "Task": "comp", "ext": "nk"}
    assert catalog.format("labelled", label="a_b", Task="anim", ext="nk") == "a_b_anim.nk"
    # The leftmost split wins, exactly as a plain regex would decide it.
    assert catalog.parse("a_comp_comp.nk", "labelled").fields["label"] == "a_comp"


def test_wrong_pieces_are_named_even_next_to_free_patterns(catalog):
    bad_task = "405_003_0400_grade_v006.nk"
    for kind in ("scene", "flat"):
        result = catalog.validate(bad_task, kind)
        assert codes(result.diagnostics) == [("invalid_field", "Task")], kind
        assert result.fields["version"] == 6 and result.fields["ext"] == "nk", kind
    assert catalog.validate(bad_task, "scene").fields["Shot"] == "405_003_0400"
    assert catalog.validate(bad_task, "flat").fields["FlatShot"] == "405_003_0400"
    # Inside a flat pattern there are no parts to point at; a composite names the bad one.
    bad_shot = "405_003_04-0_comp_v006.nk"
    assert codes(catalog.validate(bad_shot, "scene").diagnostics) == [("invalid_field", "shotnum")]
    assert catalog.validate(bad_shot, "scene").fields["Sequence"] == "405_003"
    assert codes(catalog.validate(bad_shot, "flat").diagnostics) == [("pattern_mismatch", None)]
    almost = "my_label_grade.nk"
    result = catalog.validate(almost, "labelled")
    assert codes(result.diagnostics) == [("invalid_field", "Task")]
    assert result.fields == {"label": "my_label", "ext": "nk"}


@pytest.mark.parametrize(
    "pattern,expected",
    [
        ("[A-Za-z0-9]+", False),
        ("[0-9]+|####", False),
        ("%0[0-9]+d", False),
        ("(?!v[0-9]+$)[a-z][A-Za-z0-9]*", False),
        (r"\w+", True),
        ("[^/]+", True),
        ("[A-Za-z0-9]+_[A-Za-z0-9]+", True),
        ("[a-z_]+", True),
        (".+", True),
        ("(?:a|b_c)", True),
        ("[^_.]+", False),
        (r"\d+", False),
        (r"\S+", True),
    ],
)
def test_rules_that_can_cross_punctuation_are_detected(pattern, expected):
    from namespec.template import pattern_may_match

    assert pattern_may_match(pattern, frozenset("_.")) is expected


def test_invalid_long_paths_fail_fast():
    import time

    # Twenty-odd slots, every one repeated, like a deep render path. The last piece is wrong.
    folder = "{root}/{Shot}/{Task}/{Shot}/{Task}/{Shot}/{Task}/renders/"
    catalog = Catalog.from_string(
        SOURCE
        + 'resource deep { name = "{Shot}_{Task}[_{label}]_v{version}.{ext}" location = "'
        + folder
        + '{Shot}_{Task}[_{label}]_v{version}/{name}" }'
    )
    segment = "405_003_0400/comp/"
    bad = "/Volumes/" + segment * 3 + "renders/405_003_0400_comp_mask_v014/"
    bad += "405_003_0400_comp_mask_v014.nk.bak"
    started = time.perf_counter()
    for _ in range(50):
        assert catalog.inspect(bad, source="location").status == "invalid"
    assert time.perf_counter() - started < 2.0, "fallback matching must not backtrack explosively"


def test_path_separators_stay_reserved(catalog):
    with pytest.raises(NameSpecError) as exc:
        catalog.format("labelled", label="a/b", Task="comp", ext="nk")
    assert codes(exc.value.diagnostics) == [("invalid_field", "label")]
    loose = Catalog.from_string(
        'spec 1 part = text matching "[^.]+" examples "x" resource r { name = "{part}.txt" }'
    )
    with pytest.raises(NameSpecError) as exc:
        loose.format("r", part="a/b")
    assert codes(exc.value.diagnostics) == [("reserved_separator", "part")]


def test_path_objects_are_accepted_wherever_text_is(catalog):
    windows = PureWindowsPath(r"C:\projects\405_003_0400\405_003_0400_comp_v006.nk")
    resource = catalog.parse(windows, source="location")
    assert resource.fields["root"] == "C:/projects" and resource.fields["Shot"] == "405_003_0400"
    posix = PurePosixPath("/Volumes/405_003_0400/405_003_0400_comp_v006.nk")
    assert catalog.inspect(posix, source="location").status == "valid"
    assert catalog.validate(Path("405_003_0400_comp_v006.nk"), "scene").valid
    assert catalog.normalize(PureWindowsPath(r"C:\a\b")) == "C:/a/b"
    with pytest.raises(TypeError):
        catalog.parse(42)  # type: ignore[arg-type]


def test_single_field_validation_and_spelling(catalog):
    assert catalog.validate_field("Task", "comp").fields == {"Task": "comp"}
    assert codes(catalog.validate_field("Task", "grade").diagnostics) == [("invalid_field", "Task")]
    version = catalog.validate_field("version", "006")
    assert version.fields == {"version": 6} and version.source == "field"
    assert codes(catalog.validate_field("version", "6").diagnostics) == [
        ("noncanonical_field", "version")
    ]
    assert catalog.validate_field("Shot", "405_003_0400").fields == {
        "Episode": "405",
        "seqnum": "003",
        "shotnum": "0400",
        "Sequence": "405_003",
    }
    assert codes(catalog.validate_field("Shot", "405_003").diagnostics) == [
        ("pattern_mismatch", None)
    ]
    assert catalog.format_field("version", 6) == "006"
    assert catalog.format_field("Task", "comp") == "comp"
    assert catalog.format_field("Shot", "405_003_0400") == "405_003_0400"
    for name, value, code in (
        ("version", "6", "invalid_type"),
        ("Task", "grade", "invalid_field"),
        ("Shot", "405-003", "pattern_mismatch"),
        ("nope", "x", "unknown_field"),
    ):
        with pytest.raises(NameSpecError) as exc:
            catalog.format_field(name, value)
        assert exc.value.diagnostics[0].code == code
    with pytest.raises(NameSpecError) as exc:
        catalog.validate_field("nope", "x")
    assert exc.value.diagnostics[0].code == "unknown_field"


def test_rules_load_from_the_environment_once_per_process(tmp_path, monkeypatch):
    rules = tmp_path / "studio.names"
    rules.write_text(SOURCE, encoding="utf-8")
    fallback = tmp_path / "fallback.names"
    fallback.write_text('spec 1 x = one of "a" resource only { name = "{x}" }', encoding="utf-8")
    load_rules.cache_clear()
    monkeypatch.delenv("NAMESPEC_RULES", raising=False)
    with pytest.raises(NameSpecError) as exc:
        load_rules()
    assert exc.value.diagnostics[0].code == "missing_rules"
    assert "only" in Catalog.from_env(default=fallback).definition.resources
    monkeypatch.setenv("NAMESPEC_RULES", str(rules))
    first = load_rules()
    assert "scene" in first.definition.resources
    assert load_rules() is first, "memoized"
    assert Catalog.from_env(default=fallback) is not first, "a different default is a new key"
    load_rules.cache_clear()
    assert load_rules() is not first
    load_rules.cache_clear()
