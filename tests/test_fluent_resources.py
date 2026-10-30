"""The discoverable parse, inspect, derive and pathlib workflow."""

from pathlib import Path, PureWindowsPath

import pytest

from namespec import Catalog, NameSpecError, Resource

GUIDE = Path(__file__).parents[1] / "examples" / "guide.names"
MODEL = "Donut_high_v004.abc"
LOCATION = "J:/jobs/show17/assets/Donut/high/" + MODEL


@pytest.fixture
def catalog():
    return Catalog.from_file(GUIDE)


def test_parse_result_is_an_introspectable_mapping(catalog):
    model = catalog.parse(MODEL)
    assert model.kind == "model"
    assert model.source == "name"
    assert model["version"] == 4
    assert model.get("tag") is None
    assert set(model.keys()) == {"asset", "lod", "version", "ext"}
    assert dict(model.items()) == model.fields
    assert len(model) == 4
    with pytest.raises(KeyError):
        _ = model["missing"]
    with pytest.raises(TypeError):
        model["version"] = 9
    copied = model.fields
    copied["version"] = 9
    assert model["version"] == 4
    assert "source='name'" in repr(model)


def test_definitions_are_available_without_private_implementation_knowledge(catalog):
    model = catalog.parse(MODEL)
    assert "model" in catalog.resources
    assert catalog.fields["lod"].choices == ("low", "mid", "high")
    assert model.definition is catalog.resources["model"]
    assert model.definition.location.startswith("{root}")
    with pytest.raises(TypeError):
        catalog.resources["other"] = model.definition
    with pytest.raises(TypeError):
        catalog.fields["other"] = catalog.fields["lod"]


def test_basename_path_stays_relative_until_context_is_supplied(catalog):
    model = catalog.parse(MODEL)
    assert model.path == Path(MODEL)
    assert Path(model) == model.path
    assert model.root is None
    assert model.root_name is None
    assert model.missing_context == ("root", "job")
    located = model.with_context(root="windows", job="show17")
    assert located.path == Path(LOCATION)
    assert located.source == "location"
    assert located.root == Path("J:/jobs")
    assert located.root_name == "windows"
    assert located.missing_context == ()
    assert located["job"] == "show17"
    assert model.source == "name"
    assert "job" not in model
    assert located.path.parent == Path(LOCATION).parent
    assert located.path.suffix == ".abc"
    assert located.path.stem == "Donut_high_v004"
    assert isinstance(model.locate(root="windows", job="show17"), Path)
    assert isinstance(catalog.locate("model", model, root="windows", job="show17"), Path)


def test_native_paths_and_pure_windows_inputs(catalog):
    for text in (LOCATION, Path(LOCATION), PureWindowsPath(LOCATION)):
        model = catalog.parse(text)
        assert model.path == Path(LOCATION)
        assert model.locate(root="windows") == Path(LOCATION)
        assert model.with_context(root=Path("J:/jobs")).path == Path(LOCATION)
    assert catalog.root_name(Path("J:/jobs")) == "windows"
    path = catalog.locate("model", catalog.parse(MODEL), root=Path("J:/jobs"), job="show17")
    assert path == Path(LOCATION)


def test_path_creation_is_lazy_and_does_not_access_filesystem(catalog, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected filesystem access")

    for method in ("stat", "exists", "resolve", "open"):
        monkeypatch.setattr(Path, method, forbidden)
    model = catalog.parse(LOCATION)
    assert model.path == Path(LOCATION)
    assert model.root == Path("J:/jobs")
    assert model.replace(version=5).path.name == "Donut_high_v005.abc"
    assert model.with_context().path == model.path


@pytest.mark.parametrize(
    ("context", "code"),
    [
        ({"job": "show17"}, "missing_field"),
        ({"root": "windows", "job": "show17", "asset": "Chair"}, "context_conflict"),
        ({"root": "windows", "job": "show17", "jbo": "typo"}, "unknown_field"),
        ({"root": "windows", "job": "UPPER"}, "invalid_field"),
    ],
)
def test_context_fails_usefully_instead_of_mutating_the_resource(catalog, context, code):
    model = catalog.parse(MODEL)
    with pytest.raises(NameSpecError) as caught:
        model.with_context(**context)
    assert code in {item.code for item in caught.value.diagnostics}
    assert model.path == Path(MODEL)


def test_fluent_chain_preserves_context_and_bound_class(catalog):
    @catalog.resource("model")
    class Model(Resource):
        pass

    model = catalog.parse(MODEL)
    updated = model.with_context(root="windows", job="show17").replace(version=5)
    assert isinstance(updated, Model)
    assert updated["job"] == "show17"
    assert updated.path == Path(LOCATION.replace("v004", "v005"))
    assert model["version"] == 4
    assert model.root is None


def test_related_resources_are_objects_with_their_own_bindings(catalog):
    @catalog.resource("render")
    class Render(Resource):
        pass

    scene = catalog.parse("101_120_0040_comp_v003.nk").with_context(root="windows", job="show17")
    render = scene.related("render", frame="####", image_ext="exr")
    folder = scene.related("task_folder")
    assert isinstance(render, Render)
    assert render.path.name == "101_120_0040_comp_v003.####.exr"
    assert render.path.parent.name == "v003"
    assert folder.source == "location"
    assert folder.path == scene.path.parent
    assert scene["version"] == 3
    assert scene.related("render", frame="1001", image_ext="exr", version=4)["version"] == 4
    with pytest.raises(NameSpecError) as caught:
        scene.related("unknown")
    assert caught.value.diagnostics[0].code == "unknown_resource"


def test_name_only_related_resource_and_colliding_field_names():
    catalog = Catalog.from_string("""
    spec 1
    kind = one of "sample"
    path = one of "hello"
    resource original { name = "{kind}_{path}.txt" }
    resource copy { name = "{path}_{kind}.bak" }
    """)
    resource = catalog.parse("sample_hello.txt")
    assert resource["path"] == "hello"
    assert resource["kind"] == "sample"
    assert resource.path == Path("sample_hello.txt")
    assert resource.missing_context == ()
    related = resource.related("copy", kind="sample")
    assert related.source == "name"
    assert related.path == Path("hello_sample.bak")
    with pytest.raises(NameSpecError) as caught:
        resource.with_context()
    assert caught.value.diagnostics[0].code == "missing_location"


def test_missing_context_accounts_for_partly_present_optional_groups():
    catalog = Catalog.from_string("""
    spec 1
    item = one of "a"
    tag = one of "jm"
    purpose = one of "review"
    resource file {
        name = "{item}[_{tag}].txt"
        location = "files/{item}[_{tag}_{purpose}]/{name}"
    }
    """)
    assert catalog.parse("a.txt").missing_context == ()
    tagged = catalog.parse("a_jm.txt")
    assert tagged.missing_context == ("purpose",)
    assert tagged.with_context(purpose="review").path == Path("files/a_jm_review/a_jm.txt")


def test_reader_receives_a_path_and_is_not_called_until_read():
    catalog = Catalog.from_string("""
    spec 1
    item = one of "hello"
    ext = one of "txt"
    readers { txt = "text" }
    resource note { name = "{item}.{ext}" location = "notes/{name}" reader = readers[ext] }
    """)
    calls = []
    catalog.register_reader("text", lambda path: calls.append(path) or "contents")
    note = catalog.parse("hello.txt")
    located = note.with_context()
    assert located.path == Path("notes/hello.txt")
    assert calls == []
    assert located.read() == "contents"
    assert calls == [Path("notes/hello.txt")]


def test_string_input_is_checked_before_pathlib_collapses_dot_components():
    pytest.importorskip("pathvalidate")
    catalog = Catalog.from_string(
        """
    spec 1
    item = text matching "[a-z]+"
    resource file { location = "./{item}" }
    """,
        filesystem="portable",
    )
    with pytest.raises(NameSpecError) as caught:
        catalog.parse("./hello")
    assert caught.value.diagnostics[0].code == "no_match"
    with pytest.raises(NameSpecError) as caught:
        catalog.locate("file", item="hello")
    assert caught.value.diagnostics[0].code == "unsafe_path"


def test_bytes_pathlike_input_is_rejected_cleanly(catalog):
    class BytesPath:
        def __fspath__(self):
            return b"Donut_high_v004.abc"

    with pytest.raises(TypeError, match="string or a path object"):
        catalog.parse(BytesPath())
