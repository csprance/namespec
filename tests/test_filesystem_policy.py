"""Filesystem policy is explicit, platform independent, and never sanitizes names."""

import builtins

import pytest

from namespec import Catalog, NameSpecError
from namespec.policies import check_filesystem_policy, filesystem_diagnostics


def test_missing_filesystem_extra_is_actionable(monkeypatch):
    original = builtins.__import__

    def without_extra(name, *args, **kwargs):
        if name == "pathvalidate":
            raise ImportError("not installed")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_extra)
    check_filesystem_policy(None)
    with pytest.raises(NameSpecError) as raised:
        check_filesystem_policy("portable")
    assert raised.value.diagnostics[0].code == "unavailable_filesystem_policy"


@pytest.fixture
def filesystem():
    pytest.importorskip("pathvalidate")


@pytest.mark.usefixtures("filesystem")
@pytest.mark.parametrize(
    "value", ["..", ".", "CON", "nul.txt", "LPT1.abc", "a.", "a ", "a:b", "a\t"]
)
def test_portable_policy_rejects_unsafe_components(value):
    [diagnostic] = filesystem_diagnostics(value, "portable")
    assert diagnostic.code == "unsafe_path"
    assert diagnostic.actual == value and diagnostic.span == (0, len(value))


@pytest.mark.usefixtures("filesystem")
def test_platform_is_explicit_and_locations_keep_spans():
    assert not filesystem_diagnostics("CON.txt", "posix")
    assert not filesystem_diagnostics("c:/jobs/Chair/model.abc", "windows", source="location")
    assert not filesystem_diagnostics("//server/share/Chair.abc", "portable", source="location")
    text = "C:/jobs/../CON.txt"
    problems = filesystem_diagnostics(text, "windows", source="location")
    assert [text[slice(*item.span)] for item in problems] == ["..", "CON.txt"]


@pytest.mark.usefixtures("filesystem")
def test_catalog_checks_parsing_and_generation_only_when_enabled():
    source = (
        'spec 1 x = text matching "[^/]+" resource r { name = "{x}" location = "/jobs/{name}" }'
    )
    assert Catalog.from_string(source).parse("CON.txt").fields == {"x": "CON.txt"}
    catalog = Catalog.from_string(source, filesystem="portable")
    assert catalog.validate("CON.txt", "r").diagnostics[0].code == "unsafe_path"
    with pytest.raises(NameSpecError) as raised:
        catalog.locate("r", x="..")
    assert raised.value.diagnostics[0].code == "unsafe_path"
    assert catalog.locate("r", x="Chair.abc").as_posix() == "/jobs/Chair.abc"
