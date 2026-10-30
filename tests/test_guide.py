"""Executable tutorial examples and the behavior of examples/guide.names."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from namespec import Catalog, NameSpecError, Resource, load_rules
from namespec.cli import main

GUIDE = Path(__file__).parents[1] / "examples" / "guide.names"
TUTORIAL = GUIDE.parents[1] / "docs" / "guide.md"
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


def guide_block(start):
    """The tutorial code block that starts with ``start``."""
    for block in re.findall(r"```\w*\n(.*?)```", TUTORIAL.read_text(encoding="utf-8"), re.S):
        if block.startswith(start):
            return block
    raise AssertionError(f"Tutorial has no block starting {start!r}")


def test_3_examples_are_tests(catalog, capsys, tmp_path, monkeypatch):
    assert catalog.check_examples() == []
    assert main([str(GUIDE), "test"]) == 0
    assert capsys.readouterr().out == "9 passed\n"
    # rules.names is the first file with the example blocks appended.
    monkeypatch.chdir(tmp_path)
    rules = guide_block("spec 1\n") + "\n" + guide_block("example model {\n")
    Path("rules.names").write_text(rules, encoding="utf-8")
    assert main(["rules.names", "test"]) == 0
    assert capsys.readouterr().out == guide_block("3 passed")
    Path("rules.names").write_text(rules.replace('"mid", "high"', '"mid", "hi"'), encoding="utf-8")
    assert main(["rules.names", "test"]) == 1
    assert capsys.readouterr().out == guide_block("rules.names:13:13:")
    wrong = rules.replace('lod = "high"', 'lod = "mid"')
    assert Catalog.from_string(wrong).check_examples()[0].message == (
        'Expected lod = "mid", got "high".'
    )


def test_4_where_it_lives(catalog):
    located = catalog.parse("/Volumes/jobs/show17/assets/Donut/high/Donut_high_v004.abc")
    assert located.fields["job"] == "show17" and located.fields["root"] == "/Volumes/jobs"
    clash = catalog.validate("/Volumes/jobs/show17/assets/Chair/high/Donut_high_v004.abc", "model")
    [diagnostic] = clash.diagnostics
    assert (diagnostic.code, diagnostic.field) == ("conflicting_field", "asset")
    assert (diagnostic.expected, diagnostic.actual) == ("Chair", "Donut")
    model = catalog.parse("Donut_high_v004.abc")
    assert model.locate(job="show17", root="mac") == Path(
        "/Volumes/jobs/show17/assets/Donut/high/Donut_high_v004.abc"
    )


def test_5_roots(catalog):
    windows = "J:/jobs/show17/assets/Donut/high/Donut_high_v004.abc"
    assert catalog.parse(windows).fields["root"] == "J:/jobs"
    fields = catalog.parse("Donut_high_v004.abc").fields
    assert catalog.locate("model", fields, job="show17", root="windows") == Path(windows)
    assert catalog.locate("model", fields, job="show17", root="J:/jobs") == Path(windows)
    other = catalog.validate("/mnt/show17/assets/Donut/high/Donut_high_v004.abc", "model")
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
    result = catalog.validate(wrong, "scene")
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
    folder = catalog.parse("J:/jobs/show17/shots/101/101_120/101_120_0040/comp")
    assert folder.kind == "task_folder" and folder.fields["Task"] == "comp"
    assert all(m.resource != "task_folder" for m in catalog.inspect("comp").matches)
    with pytest.raises(NameSpecError):
        catalog.format("task_folder", folder.fields)


def test_9_paths_pasted_from_windows(catalog):
    pasted = r"j:\jobs\show17\shots\101\101_120\101_120_0040\comp\101_120_0040_comp_v003.nk"
    scene = catalog.parse(pasted)
    assert scene.fields["root"] == "J:/jobs"
    assert scene.locate() == Path(
        "J:/jobs/show17/shots/101/101_120/101_120_0040/comp/101_120_0040_comp_v003.nk"
    )


def test_10_extra_facts_for_tools(catalog):
    assert catalog.parse(SCENE).metadata == {
        "entities": ("Episode", "Sequence", "Shot", "Task"),
        "kind": "workfile",
    }


def test_11_from_python(catalog):
    scene = catalog.parse(SCENE)
    assert scene.kind == "scene"
    assert scene.fields["Shot"] == "101_120_0040" and scene.fields["version"] == 3
    assert scene.metadata["kind"] == "workfile"
    assert catalog.locate("render", scene, frame="####", image_ext="exr") == Path(
        "/Volumes/jobs/show17/shots/101/101_120/101_120_0040/comp/renders/v003/"
        "101_120_0040_comp_v003.####.exr"
    )
    assert catalog.format("scene", scene.fields, version=4) == "101_120_0040_comp_v004.nk"
    assert catalog.locate("task_folder", scene).parts[-2:] == ("101_120_0040", "comp")
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
            return self.related("render", frame=frame, image_ext=image_ext).path

        def next_version(self):
            return self.replace(version=self["version"] + 1)

    scene = catalog.parse(SCENE)
    assert type(scene) is Scene
    assert scene.render_path().parts[-3:] == ("renders", "v003", "101_120_0040_comp_v003.####.exr")
    assert scene.next_version().name == "101_120_0040_comp_v004.nk"
    assert type(scene.next_version()) is Scene
    assert type(catalog.parse("Donut_high_v004.abc")) is Resource


def test_13_everywhere_a_name_is_written_or_read(monkeypatch):
    monkeypatch.delenv("STUDIO_NAMES", raising=False)
    load_rules.cache_clear()
    catalog = load_rules("STUDIO_NAMES", default=GUIDE)
    assert "scene" in catalog.resources
    assert load_rules("STUDIO_NAMES", default=GUIDE) is catalog
    load_rules.cache_clear()


def test_fluent_workflow_retains_context_and_derives_related_resources(catalog):
    scene = catalog.parse("101_120_0040_comp_v003.nk")
    assert scene.source == "name"
    assert scene.path == Path("101_120_0040_comp_v003.nk")
    assert Path(scene) == scene.path
    assert scene["version"] == 3 and scene.get("tag") is None
    assert dict(scene.items()) == scene.fields
    assert scene.missing_context == ("root", "job")
    assert scene.root is None and scene.root_name is None
    assert scene.definition is catalog.resources["scene"]
    assert "version" in catalog.fields

    located = scene.with_context(root="mac", job="show17")
    assert located.source == "location" and located.path == Path(SCENE)
    assert Path(located) == located.path
    assert located.root == Path("/Volumes/jobs") and located.root_name == "mac"
    assert located.missing_context == ()
    assert scene.source == "name" and "job" not in scene

    updated = located.replace(shotnum="0041", version=4)
    assert updated.path == Path(SCENE.replace("0040", "0041").replace("v003", "v004"))
    assert updated["job"] == "show17" and located.path == Path(SCENE)
    assert updated.replace(root="windows").root == Path("J:/jobs")

    render = updated.related("render", frame="####", image_ext="exr")
    assert render.source == "location" and render.kind == "render"
    assert render["version"] == 4 and render["Shot"] == "101_120_0041"
    assert render.path.parts[-3:] == ("renders", "v004", "101_120_0041_comp_v004.####.exr")
    assert updated.related("task_folder").path == updated.path.parent


def tutorial_scripts():
    """Collect the complete Python scripts readers are invited to run."""
    for document in (
        TUTORIAL,
        GUIDE.parents[1] / "README.md",
        GUIDE.parent / "studio.md",
        TUTORIAL.with_name("reference.md"),
    ):
        for section in re.split(r"(?m)(?=^## )", document.read_text(encoding="utf-8")):
            heading = section.splitlines()[0]
            for index, script in enumerate(re.findall(r"```python\n(.*?)```", section, re.S)):
                if document.name == "reference.md" and not script.startswith(
                    "from namespec import"
                ):
                    continue  # API fragments without their setup are not standalone scripts.
                yield pytest.param(
                    document, heading, script, id=f"{document.name}:{heading}:{index}"
                )


@pytest.mark.parametrize("document,heading,script", list(tutorial_scripts()))
def test_documented_python_scripts(document, heading, script, tmp_path, monkeypatch, capsys):
    """Run each script independently with only the files introduced at that step."""
    if heading.startswith("## 14."):
        pytest.importorskip("pathvalidate")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("STUDIO_NAMES", raising=False)
    rules = guide_block("spec 1\n")
    if heading.startswith(("## 6.", "## 7.")):
        rules = (
            rules.split("resource model {")[0]
            + guide_block("job = text matching ")
            + "\n"
            + guide_block("resource model {\n")
        )
    if heading.startswith("## 7."):
        rules = rules.replace("spec 1\n", "spec 1\n" + guide_block("roots {\n"))
        rules = rules.replace('"/jobs/{job}', '"{root}/{job}')
    Path("rules.names").write_text(rules, encoding="utf-8")
    Path("examples").mkdir()
    Path("examples/guide.names").write_bytes(GUIDE.read_bytes())
    Path("examples/studio.names").write_bytes((GUIDE.parent / "studio.names").read_bytes())
    load_rules.cache_clear()
    try:
        exec(compile(script, str(document), "exec"), {"__name__": "__main__"})
        output = capsys.readouterr().out
        if document.name != "studio.md":
            assert output
        if heading.startswith("## 13."):
            assert output == "non_roundtripping_value\n"
        elif heading.startswith("## 14."):
            assert output == "False\nunsafe_path\n"
        elif heading.startswith("## 5.") and "model = " in script:
            assert output == "model\n4\nDonut_high_v005.abc\n"
        elif heading.startswith("## 6."):
            assert output == (
                "Donut_high_v004.abc\n('job',)\n"
                "/jobs/show17/assets/Donut/high/Donut_high_v004.abc\nshow17\n"
            )
        elif heading.startswith("## 7."):
            assert output == (
                "J:/jobs/show17/assets/Donut/high/Donut_high_v004.abc\nJ:/jobs\nwindows\n"
            )
        elif heading == "## When to select a source":
            assert output == "True\nTrue\nFalse\nFalse\nTrue\n"
    finally:
        load_rules.cache_clear()
