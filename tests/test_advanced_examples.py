from pathlib import Path

from namespec import Catalog


def test_advanced_examples_and_composite_edits():
    path = Path(__file__).parents[1] / "examples" / "advanced.names"
    catalog = Catalog.from_file(path, strict=True)
    assert not catalog.check_examples()
    render = catalog.parse("Sky_Depot_jm_review_v002.0010.exr", "render")
    changed = render.replace(asset="Moon_Base", frame=-1)
    assert changed.name == "Moon_Base_jm_review_v002.-0001.exr"
    assert changed.locate(root="windows").as_posix() == (
        "J:/jobs/Moon_Base/renders/Moon_Base_jm_review_v002.-0001.exr"
    )
    for name in catalog.samples("render", limit=12):
        assert catalog.validate(name, "render").valid
