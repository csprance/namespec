"""Every claim the README makes about examples/guide.names, in the order it makes them."""

from __future__ import annotations

from pathlib import Path

import pytest

from namespec import Catalog, NameSpecError, Resource, load_rules
from namespec.cli import main

GUIDE = Path(__file__).parents[1] / "examples" / "guide.names"
SCENE = "/Volumes/jobs/show17/shots/101/101_120/101_120_0040/comp/101_120_0040_comp_v003.nk"


@pytest.fixture(scope="module")
def catalog():
    return Catalog.from_file(GUIDE)


def test_1_a_name_is_a_sentence_with_blanks(catalog):
    model = catalog.parse("Donut_high_v004.abc")
    assert model.kind == "model"
    assert model.fields == {"asset": "Donut", "lod": "high", "version": 4, "ext": "abc"}


def test_2_blanks_have_rules_and_errors_name_the_blank(catalog):
    expected = {
        "Donut_ultra_v004.abc": ("invalid_field", "lod", {"asset", "version", "ext"}),
        "Donut_high_v4.abc": ("noncanonical_field", "version", {"asset", "lod", "ext"}),
        "donut_high_v004.abc": ("invalid_field", "asset", {"lod", "version", "ext"}),
        "Donut_high.abc": ("pattern_mismatch", None, set()),
    }
    for name, (code, field, kept) in expected.items():
        result = catalog.validate(name, "model")
        assert [(d.code, d.field) for d in result.diagnostics] == [(code, field)], name
        assert set(result.fields) == kept, name
    ultra = catalog.validate("Donut_ultra_v004.abc", "model")
    assert ultra.diagnostics[0].expected == ["low", "mid", "high"]
    assert catalog.validate("Donut_high_v4.abc", "model").diagnostics[0].expected == "004"


def test_3_examples_are_tests(catalog, capsys):
    assert catalog.check_examples() == []
    assert main([str(GUIDE), "test"]) == 0
    assert '"passed": true' in capsys.readouterr().out


def test_4_where_it_lives(catalog):
    located = catalog.parse(
        "/Volumes/jobs/show17/assets/Donut/high/Donut_high_v004.abc", source="location"
    )
    assert located.fields["job"] == "show17" and located.fields["root"] == "/Volumes/jobs"
    clash = catalog.validate(
        "/Volumes/jobs/show17/assets/Chair/high/Donut_high_v004.abc", "model", source="location"
    )
    [diagnostic] = clash.diagnostics
    assert (diagnostic.code, diagnostic.field) == ("conflicting_field", "asset")
    assert (diagnostic.expected, diagnostic.actual) == ("Chair", "Donut")
    model = catalog.parse("Donut_high_v004.abc")
    assert model.locate(job="show17", root="mac") == (
        "/Volumes/jobs/show17/assets/Donut/high/Donut_high_v004.abc"
    )


def test_5_roots(catalog):
    windows = "J:/jobs/show17/assets/Donut/high/Donut_high_v004.abc"
    assert catalog.parse(windows, source="location").fields["root"] == "J:/jobs"
    fields = catalog.parse("Donut_high_v004.abc").fields
    assert catalog.locate("model", fields, job="show17", root="windows") == windows
    assert catalog.locate("model", fields, job="show17", root="J:/jobs") == windows
    other = catalog.validate(
        "/mnt/show17/assets/Donut/high/Donut_high_v004.abc", "model", source="location"
    )
    assert other.diagnostics[0].code == "pattern_mismatch"


def test_6_names_made_of_names(catalog):
    scene = catalog.parse("101_120_0040_comp_v003.nk")
    assert scene.kind == "scene"
    assert {k: scene.fields[k] for k in ("Shot", "Sequence", "Episode", "seqnum", "shotnum")} == {
        "Shot": "101_120_0040",
        "Sequence": "101_120",
        "Episode": "101",
        "seqnum": "120",
        "shotnum": "0040",
    }
    wrong = SCENE.replace("101_120_0040", "101_125_0040")
    result = catalog.validate(wrong, "scene", source="location")
    assert {(d.code, d.field) for d in result.diagnostics} == {("conflicting_field", "seqnum")}
    whole = catalog.format("scene", Shot="101_120_0040", Task="comp", version=3, scene_ext="nk")
    parts = catalog.format(
        "scene", Episode="101", seqnum="120", shotnum="0040", Task="comp", version=3, scene_ext="nk"
    )
    assert whole == parts == "101_120_0040_comp_v003.nk"


def test_7_sometimes_a_piece_is_missing(catalog):
    plain = catalog.parse("101_120_0040_comp_v003.nk")
    tagged = catalog.parse("101_120_0040_comp_v003_jm.nk")
    assert "tag" not in plain.fields and tagged.fields["tag"] == "jm"
    assert plain.kind == tagged.kind == "scene"
    assert catalog.format("scene", tagged.fields, tag=None) == "101_120_0040_comp_v003.nk"


def test_8_folders_are_resources_too(catalog):
    folder = catalog.parse("J:/jobs/show17/shots/101/101_120/101_120_0040/comp", source="location")
    assert folder.kind == "task_folder" and folder.fields["Task"] == "comp"
    assert all(m.resource != "task_folder" for m in catalog.inspect("comp").matches)
    with pytest.raises(NameSpecError):
        catalog.format("task_folder", folder.fields)


def test_9_paths_pasted_from_windows(catalog):
    pasted = r"j:\jobs\show17\shots\101\101_120\101_120_0040\comp\101_120_0040_comp_v003.nk"
    scene = catalog.parse(pasted, source="location")
    assert scene.fields["root"] == "J:/jobs"
    assert (
        scene.locate()
        == "J:/jobs/show17/shots/101/101_120/101_120_0040/comp/101_120_0040_comp_v003.nk"
    )


def test_10_extra_facts_for_tools(catalog):
    assert catalog.parse(SCENE, source="location").metadata == {
        "entities": ("Episode", "Sequence", "Shot", "Task"),
        "kind": "workfile",
    }


def test_11_from_python(catalog):
    scene = catalog.parse(SCENE, source="location")
    assert scene.kind == "scene"
    assert scene.fields["Shot"] == "101_120_0040" and scene.fields["version"] == 3
    assert scene.metadata["kind"] == "workfile"
    assert catalog.locate("render", scene.fields, frame="####", image_ext="exr") == (
        "/Volumes/jobs/show17/shots/101/101_120/101_120_0040/comp/renders/v003/"
        "101_120_0040_comp_v003.####.exr"
    )
    assert catalog.format("scene", scene.fields, version=4) == "101_120_0040_comp_v004.nk"
    assert catalog.locate("task_folder", scene.fields).endswith("/101_120_0040/comp")
    result = catalog.validate("Donut_ultra_v004.abc", "model")
    assert not result.valid
    assert (result.diagnostics[0].code, result.diagnostics[0].field) == ("invalid_field", "lod")
    assert result.fields == {"asset": "Donut", "version": 4, "ext": "abc"}
    assert catalog.inspect("101_120_0040_comp_v003.nk").status == "valid"
    assert catalog.validate_field("Shot", "101_120_0040").valid
    assert list(catalog.samples("model", limit=3)) == [
        "Donut_low_v001.abc",
        "Donut_low_v001.usd",
        "Donut_low_v002.abc",
    ]
    assert catalog.parse(Path("Donut_high_v004.abc"), "model").fields["asset"] == "Donut"


def test_12_teach_it_your_studios_tricks():
    catalog = Catalog.from_file(GUIDE)

    @catalog.resource("scene")
    class Scene(Resource):
        def render_path(self, frame="####", image_ext="exr"):
            return self.catalog.locate("render", self.fields, frame=frame, image_ext=image_ext)

        def next_version(self):
            return self.catalog.format("scene", self.fields, version=self.fields["version"] + 1)

    scene = catalog.parse(SCENE, source="location")
    assert type(scene) is Scene
    assert scene.render_path().endswith("/renders/v003/101_120_0040_comp_v003.####.exr")
    assert scene.next_version() == "101_120_0040_comp_v004.nk"
    assert type(catalog.parse("Donut_high_v004.abc")) is Resource


def test_13_everywhere_a_name_is_written_or_read(monkeypatch):
    monkeypatch.delenv("STUDIO_NAMES", raising=False)
    load_rules.cache_clear()
    catalog = load_rules("STUDIO_NAMES", default=GUIDE)
    assert "scene" in catalog.definition.resources
    assert load_rules("STUDIO_NAMES", default=GUIDE) is catalog
    load_rules.cache_clear()
