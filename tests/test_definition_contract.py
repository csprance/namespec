"""Definition state stays stable after compilation and export remains ordinary JSON."""

import json
from dataclasses import replace

import pytest

from namespec import Catalog, NameSpecError
from namespec.models import Definition, FieldSpec, ResourceSpec


def test_definitions_copy_and_freeze_caller_owned_state():
    fields = {"x": FieldSpec("x", "enum", choices=("a",))}
    metadata = {"tags": ["workfile"]}
    resources = {"r": ResourceSpec("r", "{x}", metadata=metadata)}
    definition = Definition(1, fields, resources, {}, ())
    catalog = Catalog(definition)
    fields.clear()
    resources.clear()
    metadata["tags"].append("changed")
    assert catalog.parse("a").metadata == {"tags": ("workfile",)}
    with pytest.raises(TypeError):
        definition.fields["x"] = FieldSpec("x", "text", pattern=".*")
    with pytest.raises(TypeError):
        definition.resources["r"].metadata["tags"] = ()
    exported = json.loads(json.dumps(definition.to_dict()))
    exported["resources"]["r"]["metadata"]["tags"].append("export edit")
    assert catalog.parse("a").metadata == {"tags": ("workfile",)}
    assert "spans" not in exported
    assert replace(definition, roots={"win": "C:/jobs"}).roots == {"win": "C:/jobs"}


def test_examples_cannot_be_mutated_through_the_shared_definition():
    catalog = Catalog.from_string("""spec 1
    x = one of "a"
    resource r { name = "{x}" }
    example r { input = "a" expect { x = "a" } }
    """)
    with pytest.raises(TypeError):
        catalog.definition.examples[0].expected["x"] = "b"
    assert not catalog.check_examples()


@pytest.mark.parametrize("rule", ["minimum 4 maximum 3", "minimum 0 padded to -1 digits"])
def test_invalid_integer_definitions_are_located(rule):
    with pytest.raises(NameSpecError) as raised:
        Catalog.from_string(f'spec 1 n = integer {rule} resource r {{ name = "{{n}}" }}')
    assert raised.value.diagnostics[0].code == "invalid_integer"
    assert raised.value.diagnostics[0].span is not None


def test_signed_and_bounded_integer_model_exports():
    catalog = Catalog.from_string("""spec 1
    frame = integer minimum -100 maximum 100 padded to 4 digits
    resource r { name = "{frame}" }
    """)
    model = catalog.definition.to_dict()["fields"]["frame"]
    assert (model["minimum"], model["maximum"], model["width"]) == (-100, 100, 4)


def test_oversized_regex_repeats_are_definition_errors():
    with pytest.raises(NameSpecError) as raised:
        Catalog.from_string(
            'spec 1 x = text matching "a{999999999999999999999}" resource r { name = "{x}" }'
        )
    assert raised.value.diagnostics[0].code == "invalid_pattern"
    assert raised.value.diagnostics[0].span is not None
