"""Composite fields, declared roots and location examples: the spec 1 structural constructs."""

from __future__ import annotations

import pytest

from namespec import Catalog, NameSpecError

SOURCE = """spec 1
roots {
    mac     = "/Volumes"
    windows = "C:/Program Files/jobs"
}
project_number = text matching "[0-9]+" examples "1000"
project_name   = text matching "[A-Za-z0-9]+" examples "TestShow"
project_code   = "{project_number}_{project_name}"
Episode  = text matching "[A-Za-z0-9]+" examples "405"
seqnum   = text matching "[0-9]+" examples "003"
shotnum  = text matching "[0-9]+" examples "0400"
Sequence = "{Episode}_{seqnum}"
Shot     = "{Sequence}_{shotnum}"
Task     = one of "comp", "anim"
version  = integer minimum 0 padded to 3 digits
ext      = text matching "[a-z0-9]+" examples "nk"

resource shot_work_scene {
    name     = "{Shot}_{Task}_v{version}.{ext}"
    location = "{root}/{project_code}/shots/{Episode}/{Sequence}/{Shot}/work/{Task}/scenes/{name}"
}
"""
PATH = (
    "/Volumes/1000_TestShow/shots/405/405_003/405_003_0400/work/comp/scenes/"
    "405_003_0400_comp_v006.nk"
)
FIELDS = {
    "Episode": "405",
    "seqnum": "003",
    "shotnum": "0400",
    "Sequence": "405_003",
    "Shot": "405_003_0400",
    "Task": "comp",
    "version": 6,
    "ext": "nk",
}


def codes(diagnostics):
    return [(item.code, item.field, item.composite) for item in diagnostics]


@pytest.fixture(scope="module")
def catalog():
    return Catalog.from_string(SOURCE)


def test_composites_parse_to_parts_and_joined_values(catalog):
    resource = catalog.parse("405_003_0400_comp_v006.nk")
    assert resource.fields == FIELDS
    assert resource.name == "405_003_0400_comp_v006.nk"
    located = catalog.parse(PATH, source="location")
    assert located.fields == {
        **FIELDS,
        "root": "/Volumes",
        "project_code": "1000_TestShow",
        "project_number": "1000",
        "project_name": "TestShow",
    }
    assert located.locate() == PATH
    assert catalog.inspect(PATH, source="location").status == "valid"
    exported = catalog.definition.to_dict()["fields"]["Shot"]
    assert exported["kind"] == "composite" and exported["template"] == "{Sequence}_{shotnum}"


def test_repeated_composites_are_checked_per_part(catalog):
    conflicting = PATH.replace("405_003_0400", "405_004_0400")
    result = catalog.validate(conflicting, "shot_work_scene", source="location")
    assert codes(result.diagnostics) == [
        ("conflicting_field", "seqnum", "Sequence"),
        ("conflicting_field", "seqnum", "Sequence"),
    ]
    for diagnostic in result.diagnostics:
        assert conflicting[slice(*diagnostic.span)] == "004"
    assert "seqnum" not in result.fields
    assert "Sequence" not in result.fields and "Shot" not in result.fields
    assert result.fields["shotnum"] == "0400" and result.fields["Episode"] == "405"
    invalid = catalog.validate("405_003_04x0_comp_v006.nk", "shot_work_scene")
    assert codes(invalid.diagnostics) == [("invalid_field", "shotnum", "Shot")]
    assert invalid.fields["Sequence"] == "405_003" and "Shot" not in invalid.fields


def test_format_accepts_composite_values_or_their_parts(catalog):
    expected = "405_003_0400_comp_v006.nk"
    assert catalog.format("shot_work_scene", Shot="405_003_0400", Task="comp", version=6, ext="nk")
    assert (
        catalog.format(
            "shot_work_scene",
            Episode="405",
            seqnum="003",
            shotnum="0400",
            Task="comp",
            version=6,
            ext="nk",
        )
        == expected
    )
    assert (
        catalog.format(
            "shot_work_scene",
            Shot="405_003_0400",
            Sequence="405_003",
            Episode="405",
            Task="comp",
            version=6,
            ext="nk",
        )
        == expected
    )
    with pytest.raises(NameSpecError) as exc:
        catalog.format(
            "shot_work_scene",
            Shot="405_003_0400",
            Sequence="405_004",
            Task="comp",
            version=6,
            ext="nk",
        )
    assert codes(exc.value.diagnostics) == [
        ("conflicting_field", "Sequence", "Shot"),
        ("conflicting_field", "seqnum", "Sequence"),
    ]
    with pytest.raises(NameSpecError) as exc:
        catalog.format("shot_work_scene", Shot="405-003-0400", Task="comp", version=6, ext="nk")
    assert codes(exc.value.diagnostics) == [("invalid_field", "Shot", None)]
    with pytest.raises(NameSpecError) as exc:
        catalog.format("shot_work_scene", Shot=405, Task="comp", version=6, ext="nk")
    assert codes(exc.value.diagnostics) == [("invalid_type", "Shot", None)]
    with pytest.raises(NameSpecError) as exc:
        catalog.format("shot_work_scene", Task="comp", version=6, ext="nk")
    assert codes(exc.value.diagnostics) == [
        ("missing_field", "Episode", "Sequence"),
        ("missing_field", "seqnum", "Sequence"),
        ("missing_field", "shotnum", "Shot"),
    ]


def test_samples_compose_from_parts(catalog):
    samples = list(catalog.samples("shot_work_scene", limit=3))
    assert samples == [
        "405_003_0400_comp_v000.nk",
        "405_003_0400_comp_v001.nk",
        "405_003_0400_anim_v000.nk",
    ]
    for name in samples:
        assert catalog.parse(name).fields["Shot"] == "405_003_0400"


def test_roots_are_literal_prefixes_tried_in_turn(catalog):
    assert catalog.roots == {"mac": "/Volumes", "windows": "C:/Program Files/jobs"}
    windows = PATH.replace("/Volumes", "C:/Program Files/jobs")
    located = catalog.parse(windows, source="location")
    assert located.fields["root"] == "C:/Program Files/jobs"
    assert catalog.root_name(located.fields["root"]) == "windows"
    assert catalog.root_name("mac") == "mac"
    with pytest.raises(NameSpecError) as exc:
        catalog.root_name("/mnt")
    assert exc.value.diagnostics[0].code == "unknown_root"
    result = catalog.validate(
        PATH.replace("/Volumes", "/mnt"), "shot_work_scene", source="location"
    )
    assert [item.code for item in result.diagnostics] == ["pattern_mismatch"]
    assert (
        catalog.inspect(PATH.replace("/Volumes", "/Volumes2"), source="location").status
        == "invalid"
    )
    fields = {**FIELDS, "project_code": "1000_TestShow"}
    assert catalog.locate("shot_work_scene", fields, root="windows") == windows
    assert catalog.locate("shot_work_scene", fields, root="/Volumes") == PATH
    for root, code in ((None, "missing_field"), ("/mnt", "invalid_field"), (3, "invalid_type")):
        with pytest.raises(NameSpecError) as exc:
            catalog.locate("shot_work_scene", fields, root=root)
        assert codes(exc.value.diagnostics) == [(code, "root", None)]
    assert exc.value.diagnostics[0].field == "root"


def test_location_examples_and_rejections_run_against_locations():
    good = Catalog.from_string(
        SOURCE
        + """
example shot_work_scene {
    location = "PATH"
    expect {
        root = "/Volumes"
        project_code = "1000_TestShow"
        project_number = "1000"
        project_name = "TestShow"
        Episode = "405"
        seqnum = "003"
        shotnum = "0400"
        Sequence = "405_003"
        Shot = "405_003_0400"
        Task = "comp"
        version = 6
        ext = "nk"
    }
}
reject shot_work_scene {
    location = "BAD"
    expect = "conflicting_field"
}
example shot_work_scene {
    input = "405_003_0400_comp_v006.nk"
    expect {
        Episode = "405"
        seqnum = "003"
        shotnum = "0400"
        Sequence = "405_003"
        Shot = "405_003_0400"
        Task = "comp"
        version = 6
        ext = "nk"
    }
}
""".replace("PATH", PATH).replace("BAD", PATH.replace("405_003_0400", "405_004_0400"))
    )
    assert good.check_examples() == []
    assert [example.source for example in good.definition.examples] == [
        "location",
        "location",
        "name",
    ]
    bad = Catalog.from_string(
        SOURCE
        + 'reject shot_work_scene { location = "PATH" expect = "conflicting_field" }'.replace(
            "PATH", PATH
        )
    )
    assert [item.code for item in bad.check_examples()] == ["example_failed"]


X = 'x = one of "1" '
NAMED = X + 'resource r { name = "{x}" }'
LOCATED = X + 'resource r { name = "{x}" location = "{root}/{name}" }'


@pytest.mark.parametrize(
    "source,code",
    [
        ('spec 1 a = "{b}" b = "{a}" resource r { name = "{a}" }', "cyclic_field"),
        ('spec 1 a = "{a}" resource r { name = "{a}" }', "cyclic_field"),
        ('spec 1 a = "{missing}" resource r { name = "{a}" }', "unknown_field"),
        (
            'spec 1 a = "{x}{y}" y = one of "2" ' + X + 'resource r { name = "{a}" }',
            "ambiguous_template",
        ),
        ('spec 1 a = "{x}" ' + X + 'resource r { name = "{a}{x}" }', "ambiguous_template"),
        ('spec 1 a = "fixed" resource r { name = "{a}" }', "invalid_template"),
        ('spec 1 a = "{x:>3}" ' + X + 'resource r { name = "{a}" }', "invalid_template"),
        ("spec 1 " + X + 'resource r { name = "{root}_{x}" }', "invalid_template"),
        ("spec 1 " + LOCATED, "missing_root"),
        ('spec 1 roots { a = "/a/" } ' + LOCATED, "invalid_root"),
        ('spec 1 roots { a = "" } ' + LOCATED, "invalid_root"),
        ('spec 1 roots { a = "C:\\\\x" } ' + LOCATED, "invalid_root"),
        ('spec 1 roots { a = "/{x}" } ' + LOCATED, "invalid_root"),
        ('spec 1 roots { a = "/a" b = "/a" } ' + LOCATED, "duplicate_root"),
        ('spec 1 roots { a = "/a" a = "/b" } ' + LOCATED, "duplicate_definition"),
        (
            'spec 1 roots { a = "/a" } ' + LOCATED.replace('"{root}/', '"/x/{root}/'),
            "invalid_template",
        ),
        (
            'spec 1 roots { a = "/a" } ' + LOCATED.replace("{root}/", "{root}/{root}/"),
            "invalid_template",
        ),
        ('spec 1 roots { a = "/a" } ' + LOCATED.replace("{root}/", "{root}"), "ambiguous_template"),
        ('spec 1 root = one of "1" resource r { name = "{root}" }', "reserved_field"),
        ("spec 1 " + NAMED + ' reject r { location = "1" expect = "x" }', "missing_location"),
    ],
)
def test_structural_definition_errors(source, code):
    with pytest.raises(NameSpecError) as exc:
        Catalog.from_string(source)
    assert [item.code for item in exc.value.diagnostics] == [code]
