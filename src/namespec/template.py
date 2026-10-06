"""Bidirectional templates with deterministic token boundaries and field diagnostics."""

from __future__ import annotations

import re
from dataclasses import replace
from string import Formatter
from typing import Any

from .models import Diagnostic, FieldSpec, NameSpecError, Validation, fail


def field_value(spec: FieldSpec, value: Any, *, parsing: bool) -> str | int:
    """Validate a logical value or decode one field's spelling in a name."""
    details = {"field": spec.name, "actual": value}
    if value is None or value == "":
        fail("missing_field", f"Missing {spec.name!r}.", **details)
    if spec.kind == "integer":
        if parsing:
            if not re.fullmatch(r"[0-9]+", value):
                fail("invalid_field", f"{spec.name!r} must contain ASCII digits.", **details)
            number = int(value)
        elif type(value) is int:
            number = value
        else:
            fail("invalid_type", f"{spec.name!r} requires an integer.", **details)
        if number < spec.minimum:
            fail(
                "invalid_field",
                f"{spec.name!r} must be at least {spec.minimum}.",
                expected=spec.minimum,
                **details,
            )
        if parsing and value != str(number).zfill(spec.width):
            fail(
                "noncanonical_field",
                f"{spec.name!r} must use canonical numeric padding.",
                expected=str(number).zfill(spec.width),
                **details,
            )
        return number
    if not isinstance(value, str):
        fail("invalid_type", f"{spec.name!r} requires text.", **details)
    if spec.kind == "enum" and value not in spec.choices:
        fail(
            "invalid_field",
            f"Invalid {spec.name!r}; expected one of {spec.choices}.",
            expected=list(spec.choices),
            **details,
        )
    if spec.kind == "text" and not re.fullmatch(spec.pattern, value):
        fail(
            "invalid_field",
            f"{spec.name!r} does not match {spec.pattern!r}.",
            expected=spec.pattern,
            **details,
        )
    return value


class Template:
    """Literal text and {field} slots. Delimiter punctuation is reserved in field values.

    Reserving delimiters keeps structural extraction independent of field validation:
    a misspelled enum can still be attached to the correct field, without guessing.
    """

    def __init__(self, text: str, fields: dict[str, FieldSpec]):
        self.text = text
        self.fields = fields
        try:
            self.parts = list(Formatter().parse(text))
        except ValueError as exc:
            fail("invalid_template", str(exc))
        self.names: list[str] = []
        punctuation: set[str] = set()
        previous_slot = False
        for literal, name, formatting, conversion in self.parts:
            punctuation.update(c for c in literal if not c.isalnum())
            if name is not None:
                if name not in fields:
                    fail("unknown_field", f"Unknown field {name!r} in {text!r}.")
                if formatting or conversion:
                    fail("invalid_template", "Put formatting rules in field definitions.")
                if previous_slot and not any(not c.isalnum() for c in literal):
                    fail("ambiguous_template", "Separate fields with literal punctuation.")
                self.names.append(name)
                previous_slot = True
        if not self.names:
            fail("invalid_template", "A template must contain at least one field.")
        self.delimiters = frozenset(punctuation | {"/", "\\", "\n", "\r"})
        allowed = "[^" + re.escape("".join(sorted(self.delimiters))) + "]*"
        expression: list[str] = []
        index = 0
        for literal, name, _, _ in self.parts:
            expression.append(re.escape(literal))
            if name is not None:
                expression.append(f"(?P<f{index}>{allowed})")
                index += 1
        self.regex = re.compile("".join(expression))

    def validate(self, text: str, resource: str, source: str = "name") -> Validation:
        match = self.regex.fullmatch(text)
        if not match:
            return Validation(
                resource,
                text,
                {},
                (
                    Diagnostic(
                        "pattern_mismatch",
                        "Input does not fit the template structure.",
                        expected=self.text,
                        actual=text,
                    ),
                ),
                source,
            )
        values: dict[str, str | int] = {}
        diagnostics: list[Diagnostic] = []
        raw_values: dict[str, str] = {}
        conflicts: set[str] = set()
        for index, name in enumerate(self.names):
            raw = match[f"f{index}"]
            span = match.span(f"f{index}")
            if name in raw_values and raw != raw_values[name]:
                conflicts.add(name)
                diagnostics.append(
                    Diagnostic(
                        "conflicting_field",
                        f"Repeated {name!r} values disagree.",
                        name,
                        raw_values[name],
                        raw,
                        span,
                    )
                )
            raw_values.setdefault(name, raw)
            try:
                values[name] = field_value(self.fields[name], raw, parsing=True)
            except NameSpecError as exc:
                diagnostics.extend(replace(item, span=span) for item in exc.diagnostics)
                conflicts.add(name)
        for name in conflicts:
            values.pop(name, None)
        return Validation(resource, text, values, tuple(diagnostics), source)

    def format(self, values: dict[str, Any]) -> str:
        rendered: dict[str, str] = {}
        diagnostics: list[Diagnostic] = []
        for name in dict.fromkeys(self.names):
            spec = self.fields[name]
            try:
                value = field_value(spec, values.get(name), parsing=False)
                spelling = str(value).zfill(spec.width) if spec.kind == "integer" else value
                if any(c in self.delimiters for c in spelling):
                    fail(
                        "reserved_separator",
                        f"{name!r} contains template delimiter punctuation.",
                        field=name,
                        actual=spelling,
                    )
                rendered[name] = spelling
            except NameSpecError as exc:
                diagnostics.extend(exc.diagnostics)
        if diagnostics:
            raise NameSpecError(diagnostics)
        return self.text.format_map(rendered)
