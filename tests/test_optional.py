"""Optional groups, folder resources and the normalize block."""

from __future__ import annotations

import pytest

from namespec import Catalog, NameSpecError

SOURCE = """spec 1
roots {
    mac = "/Volumes"
    win = "C:/projects"
}
normalize {
    slashes = "forward"
    drive = "upper"
}
Shot        = text matching "[0-9]{4}" examples "0010"
Task        = one of "comp", "anim"
description = text matching "[a-z]+" examples "mask"
tag         = text matching "[a-z]+" examples "jm"
version     = integer minimum 1 padded to 3 digits
scene_ext   = one of "nk"
render_ext  = one of "mov", "exr"

resource scene {
    name     = "{Shot}_{Task}_v{version}[_{tag}].{scene_ext}"
    location = "{root}/shots/{Shot}/work/{Task}/scenes/{name}"
}
resource render {
    name     = "{Shot}_{Task}[_{description}]_v{version}.{render_ext}"
    location = "{root}/shots/{Shot}/renders/{Shot}_{Task}[_{description}]_v{version}/{name}"
}
resource pair {
    name = "{Shot}[_{description}_{tag}].{scene_ext}"
}
resource task_folder {
    location = "{root}/shots/{Shot}/work/{Task}"
    meta { kind = "folder" }
}
example scene {
    input = "0010_comp_v001.nk"
    expect { Shot = "0010" Task = "comp" version = 1 scene_ext = "nk" }
}
example scene {
    input = "0010_comp_v001_jm.nk"
    expect { Shot = "0010" Task = "comp" version = 1 tag = "jm" scene_ext = "nk" }
}
reject render {
    location = "/Volumes/shots/0010/renders/0010_comp_mask_v001/0010_comp_v001.mov"
    expect = "conflicting_field"
}
"""


def codes(diagnostics):
    return [(item.code, item.field) for item in diagnostics]


@pytest.fixture(scope="module")
def catalog():
    return Catalog.from_string(SOURCE)


def test_optional_groups_parse_both_ways_and_absent_fields_are_omitted(catalog):
    plain = catalog.parse("0010_comp_v001.nk")
    assert plain.kind == "scene"
    assert plain.fields == {"Shot": "0010", "Task": "comp", "version": 1, "scene_ext": "nk"}
    tagged = catalog.parse("0010_comp_v001_jm.nk")
    assert tagged.fields["tag"] == "jm"
    assert catalog.inspect("0010_comp_v001.nk").status == "valid"
    described = catalog.parse("0010_comp_mask_v001.mov")
    assert described.kind == "render" and described.fields["description"] == "mask"
    assert "description" not in catalog.parse("0010_comp_v001.mov").fields
    assert catalog.check_examples() == []


def test_a_group_must_be_present_or_absent_everywhere(catalog):
    folder_only = "/Volumes/shots/0010/renders/0010_comp_mask_v001/0010_comp_v001.mov"
    result = catalog.validate(folder_only, "render", source="location")
    assert codes(result.diagnostics) == [("conflicting_field", "description")]
    # The span marks the occurrence that is present; the other occurrence has nothing to mark.
    assert result.diagnostics[0].actual == "mask" and result.diagnostics[0].expected is None
    assert folder_only[slice(*result.diagnostics[0].span)] == "mask"
    assert "description" not in result.fields and result.fields["version"] == 1
    both = folder_only.replace("0010_comp_v001.mov", "0010_comp_mask_v001.mov")
    assert catalog.parse(both, source="location").fields["description"] == "mask"


def test_format_omits_absent_groups_and_requires_a_started_group(catalog):
    base = {"Shot": "0010", "Task": "comp", "version": 1, "scene_ext": "nk"}
    assert catalog.format("scene", base) == "0010_comp_v001.nk"
    assert catalog.format("scene", base, tag=None) == "0010_comp_v001.nk"
    assert catalog.format("scene", base, tag="jm") == "0010_comp_v001_jm.nk"
    with pytest.raises(NameSpecError) as exc:
        catalog.format("scene", Shot="0010", Task="comp")
    assert codes(exc.value.diagnostics) == [
        ("missing_field", "version"),
        ("missing_field", "scene_ext"),
    ]
    assert catalog.format("pair", Shot="0010", scene_ext="nk") == "0010.nk"
    with pytest.raises(NameSpecError) as exc:
        catalog.format("pair", Shot="0010", scene_ext="nk", description="mask")
    assert codes(exc.value.diagnostics) == [("missing_field", "tag")]
    assert catalog.format("pair", Shot="0010", scene_ext="nk", description="mask", tag="jm") == (
        "0010_mask_jm.nk"
    )
    location = catalog.locate("render", base, root="mac", render_ext="mov", description="mask")
    assert location.as_posix().endswith("/renders/0010_comp_mask_v001/0010_comp_mask_v001.mov")


def test_samples_cover_both_forms(catalog):
    samples = list(catalog.samples("scene", limit=20))
    assert "0010_comp_v001.nk" in samples and "0010_comp_v001_jm.nk" in samples
    for sample in samples:
        assert catalog.parse(sample, "scene").name == sample
    assert all("_jm" in sample for sample in catalog.samples("scene", limit=5, tag="jm"))


def test_optional_composites_are_omitted_as_a_whole():
    catalog = Catalog.from_string(
        """spec 1
        Episode = text matching "[0-9]+" examples "101"
        seqnum = text matching "[0-9]+" examples "120"
        Sequence = "{Episode}_{seqnum}"
        Task = one of "comp"
        resource item { name = "{Task}[_{Sequence}].nk" }
        """
    )
    assert catalog.parse("comp.nk").fields == {"Task": "comp"}
    assert catalog.parse("comp_101_120.nk").fields["Sequence"] == "101_120"
    assert catalog.format("item", Task="comp", Sequence="101_120") == "comp_101_120.nk"
    assert catalog.format("item", Task="comp") == "comp.nk"


def test_folder_resources_only_have_locations(catalog):
    folder = catalog.parse("/Volumes/shots/0010/work/comp", source="location")
    assert folder.kind == "task_folder"
    assert folder.fields == {"root": "/Volumes", "Shot": "0010", "Task": "comp"}
    assert folder.metadata == {"kind": "folder"}
    assert folder.locate().as_posix() == "/Volumes/shots/0010/work/comp"
    assert catalog.locate("task_folder", root="win", Shot="0020", Task="anim").as_posix() == (
        "C:/projects/shots/0020/work/anim"
    )
    for call in (
        lambda: folder.name,
        lambda: catalog.format("task_folder", Shot="0010", Task="comp"),
        lambda: list(catalog.samples("task_folder")),
        lambda: catalog.validate("x", "task_folder", source="name"),
    ):
        with pytest.raises(NameSpecError) as exc:
            call()
        assert codes(exc.value.diagnostics) == [("missing_name", None)]
    assert all(match.resource != "task_folder" for match in catalog.inspect("0010").matches)
    assert catalog.inspect("/Volumes/shots/0010/work/comp", source="location").status == "valid"


def test_normalize_applies_to_locations_only(catalog):
    windows = r"c:\projects\shots\0010\work\comp\scenes\0010_comp_v001.nk"
    canonical = "C:/projects/shots/0010/work/comp/scenes/0010_comp_v001.nk"
    assert catalog.normalize(windows) == canonical
    resource = catalog.parse(windows, source="location")
    assert resource.fields["root"] == "C:/projects" and resource.locate().as_posix() == canonical
    assert catalog.validate(windows, "scene", source="location").input == canonical
    assert catalog.inspect(windows, source="location").status == "valid"
    assert catalog.normalize("a\\b", "name") == "a\\b"
    assert (
        catalog.validate("0010_comp_v001.nk\\", "scene", source="name").diagnostics[0].code
        == "pattern_mismatch"
    )
    strict = Catalog.from_string(
        SOURCE.replace('slashes = "forward"', "").replace('drive = "upper"', "")
    )
    assert (
        strict.validate(windows, "scene", source="location").diagnostics[0].code
        == "pattern_mismatch"
    )


X = 'x = one of "1" y = one of "2" '


@pytest.mark.parametrize(
    "source,code",
    [
        ("spec 1 " + X + 'resource r { name = "{x}[_{y}" }', "invalid_template"),
        ("spec 1 " + X + 'resource r { name = "{x}_{y}]" }', "invalid_template"),
        ("spec 1 " + X + 'resource r { name = "{x}[_[{y}]]" }', "invalid_template"),
        ("spec 1 " + X + 'resource r { name = "{x}[_]" }', "invalid_template"),
        ("spec 1 " + X + 'resource r { name = "{x}[{y}]" }', "ambiguous_template"),
        ("spec 1 " + X + 'resource r { name = "{x}[_{y}]{x}" }', "ambiguous_template"),
        ("spec 1 " + X + 'resource r { name = "[{x}].{y}" }', "ambiguous_template"),
        (
            'spec 1 roots { a = "/a" } '
            + X
            + 'resource r { name = "{x}" location = "[{root}]/{name}" }',
            "invalid_template",
        ),
        ("spec 1 " + X + 'resource r { location = "/{x}/{name}" }', "invalid_template"),
        (
            "spec 1 "
            + X
            + 'resource r { location = "/{x}" } example r { input = "1" expect { x = "1" } }',
            "missing_name",
        ),
        ('spec 1 a = "{x}[_{y}" ' + X + 'resource r { name = "{a}" }', "invalid_template"),
        ('spec 1 a = "[_{x}]" ' + X + 'resource r { name = "{y}[{a}]" }', "invalid_template"),
    ],
)
def test_group_and_folder_definition_errors(source, code):
    with pytest.raises(NameSpecError) as exc:
        Catalog.from_string(source)
    assert [item.code for item in exc.value.diagnostics] == [code]
