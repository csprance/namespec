"""Compile the readable language using textX, not a handwritten language parser."""

from __future__ import annotations

import re
from importlib.resources import files

from textx import TextXError, metamodel_from_str

from .models import Definition, ExampleSpec, FieldSpec, ResourceSpec, fail


def compile_definition(source: str) -> Definition:
    grammar = files("namespec").joinpath("grammar.tx").read_text(encoding="utf-8")
    try:
        model = metamodel_from_str(grammar).model_from_str(source)
    except TextXError as exc:
        fail("syntax_error", str(exc))
    if model.version != 1:
        fail("unsupported_spec", f"Unsupported specification version: {model.version}.")

    fields: dict[str, FieldSpec] = {}
    resources: dict[str, ResourceSpec] = {}
    readers: dict[str, str] = {}
    examples: list[ExampleSpec] = []
    for declaration in model.declarations:
        kind = type(declaration).__name__
        if kind == "Field":
            if declaration.name == "name":
                fail("reserved_field", "The field 'name' is reserved for the resource filename.")
            rule = declaration.rule
            rule_kind = type(rule).__name__
            if rule_kind == "TextRule":
                try:
                    regex = re.compile(rule.pattern)
                except re.error as exc:
                    fail("invalid_pattern", f"{declaration.name}: {exc}")
                if regex.fullmatch(""):
                    fail("empty_field", f"{declaration.name} must not accept an empty string.")
                spec = FieldSpec(
                    declaration.name, "text", pattern=rule.pattern, samples=tuple(rule.samples)
                )
                if any(not regex.fullmatch(value) for value in spec.samples):
                    fail("invalid_sample", f"An example violates field {spec.name!r}.")
            elif rule_kind == "IntegerRule":
                if rule.minimum < 0 or rule.width < 0:
                    fail("invalid_integer", "Minimum and padding must be nonnegative.")
                spec = FieldSpec(
                    declaration.name, "integer", minimum=rule.minimum, width=rule.width
                )
            else:
                if any(not value for value in rule.values):
                    fail("empty_field", f"{declaration.name} has an empty enum choice.")
                if len(set(rule.values)) != len(rule.values):
                    fail("duplicate_choice", f"{declaration.name} has duplicate choices.")
                spec = FieldSpec(declaration.name, "enum", choices=tuple(rule.values))
            _insert(fields, declaration.name, spec)
        elif kind == "Resource":
            _insert(
                resources,
                declaration.name,
                ResourceSpec(
                    declaration.name,
                    declaration.template,
                    declaration.location or None,
                    declaration.reader_field or None,
                ),
            )
        elif kind == "Readers":
            for entry in declaration.entries:
                if not entry.handler:
                    fail("empty_handler", "Reader handler IDs cannot be empty.")
                _insert(readers, entry.extension, entry.handler)
        else:
            expected: dict[str, str | int] = {}
            if kind == "Example":
                for entry in declaration.fields:
                    _insert(expected, entry.name, entry.value)
            examples.append(
                ExampleSpec(
                    declaration.resource,
                    declaration.input,
                    expected,
                    declaration.code if kind == "Rejection" else None,
                )
            )
    if not resources:
        fail("missing_resource", "Define at least one resource.")
    for example in examples:
        if example.resource not in resources:
            fail("unknown_resource", f"Example references unknown resource {example.resource!r}.")
    return Definition(1, fields, resources, readers, tuple(examples))


def _insert(target: dict, name: str, value: object) -> None:
    if name in target:
        fail("duplicate_definition", f"Duplicate definition: {name!r}.")
    target[name] = value
