"""Studio behavior lives on Resource subclasses bound to resource kinds; rules stay data."""

from __future__ import annotations

import pytest

from namespec import Catalog, NameSpecError, Resource

SOURCE = """spec 1
job     = text matching "[a-z0-9]+" examples "show17"
asset   = text matching "[A-Za-z][A-Za-z0-9]*" examples "Donut"
shot    = text matching "[0-9]{4}" examples "0010"
version = integer minimum 1 padded to 3 digits
ext     = one of "abc", "usd", "nk"

resource asset_model {
    name = "{asset}_v{version}.{ext}"
    location = "/jobs/{job}/assets/{asset}/{name}"
    meta { entities = ["Project", "Asset"] }
}
resource asset_alias { name = "{asset}.{ext}" }
resource shot_scene {
    name = "{shot}_v{version}.{ext}"
    location = "/jobs/{job}/shots/{shot}/{name}"
    meta { entities = ["Project", "Shot"] }
}
"""


def codes(exc):
    return [diagnostic.code for diagnostic in exc.value.diagnostics]


@pytest.fixture
def catalog():
    return Catalog.from_string(SOURCE)


def test_bound_classes_come_back_from_parse_with_their_methods(catalog):
    calls = []

    class Versioned(Resource):
        def next_version(self):
            """Where the next version of this file would live."""
            return self.catalog.locate(
                self.kind, self.fields, job="show17", version=self.fields["version"] + 1
            )

    @catalog.resource("asset_*")
    class AssetFile(Versioned):
        def sg_asset(self, sg):
            calls.append(self.fields["asset"])
            return sg(self.fields["asset"])

    @catalog.resource("shot_scene")
    class ShotFile(Versioned):
        pass

    assert AssetFile is not None and ShotFile is not None
    model = catalog.parse("Donut_v004.abc", "asset_model")
    assert type(model) is AssetFile
    assert model.fields["version"] == 4 and model.metadata["entities"] == ("Project", "Asset")
    assert model.next_version().as_posix() == "/jobs/show17/assets/Donut/Donut_v005.abc"
    assert model.sg_asset(str.upper) == "DONUT" and calls == ["Donut"]
    assert type(catalog.parse("Donut.abc")) is AssetFile
    scene = catalog.parse("0010_v001.nk")
    assert type(scene) is ShotFile and not hasattr(scene, "sg_asset")
    assert scene.next_version().as_posix().endswith("/shots/0010/0010_v002.nk")
    assert repr(scene) == (
        "ShotFile('shot_scene', {'shot': '0010', 'version': 1, 'ext': 'nk'}, source='name')"
    )
    assert catalog.resource_class("asset_alias") is AssetFile
    assert catalog.resource_class("shot_scene") is ShotFile


def test_unbound_kinds_return_plain_resources(catalog):
    assert type(catalog.parse("Donut_v004.abc", "asset_model")) is Resource
    assert catalog.resource_class("asset_model") is Resource
    with pytest.raises(NameSpecError) as exc:
        catalog.resource_class("nope")
    assert codes(exc) == ["unknown_resource"]


def test_binding_mistakes_are_reported(catalog):
    class First(Resource):
        pass

    class Second(Resource):
        pass

    catalog.bind(First, "asset_model")
    catalog.bind(First, "asset_model", "asset_alias")
    with pytest.raises(NameSpecError) as exc:
        catalog.bind(Second, "asset_*")
    assert codes(exc) == ["duplicate_binding"]
    assert exc.value.diagnostics[0].expected == "First"
    with pytest.raises(NameSpecError) as exc:
        catalog.bind(Second, "shot_scne")
    assert codes(exc) == ["unknown_resource"]
    with pytest.raises(TypeError):
        catalog.bind(object, "shot_scene")
    with pytest.raises(TypeError):
        catalog.bind(Second)
    with pytest.raises(TypeError):
        catalog.resource("shot_scene")(dict)
    assert catalog.resource_class("shot_scene") is Resource, "nothing partial was bound"
