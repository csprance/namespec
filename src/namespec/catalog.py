"""Public naming, discovery, location, and explicit reader operations."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from itertools import islice, product
from pathlib import Path
from typing import Any

from .compiler import compile_definition
from .models import Definition, Diagnostic, Inspection, NameSpecError, Validation, fail
from .template import Template


class Catalog:
    def __init__(self, definition: Definition):
        self.definition = definition
        self._names: dict[str, Template] = {}
        self._locations: dict[str, Template] = {}
        self._readers: dict[str, Callable[[Path], Any]] = {}
        for name, spec in definition.resources.items():
            template = Template(spec.template, definition.fields)
            self._names[name] = template
            if spec.location:
                # Expand the filename into field slots, retaining repeated-value checks.
                expanded = spec.location.replace("{name}", spec.template)
                location = Template(expanded, definition.fields)
                if not set(template.names).issubset(location.names):
                    fail(
                        "incomplete_location",
                        f"Location for {name!r} must include its name fields.",
                    )
                self._locations[name] = location
            if spec.reader_field:
                if spec.reader_field not in template.names:
                    fail("unknown_field", f"Reader field {spec.reader_field!r} is not in the name.")
                field = definition.fields[spec.reader_field]
                if field.kind != "enum":
                    fail("invalid_reader", "Reader selection requires an enum field.")
                missing = set(field.choices) - definition.readers.keys()
                if missing:
                    fail("missing_reader_mapping", f"Missing reader mappings: {sorted(missing)}.")

    @classmethod
    def from_string(cls, source: str) -> Catalog:
        return cls(compile_definition(source))

    @classmethod
    def from_file(cls, path: str | Path) -> Catalog:
        return cls.from_string(Path(path).read_text(encoding="utf-8"))

    def _template(self, resource: str, source: str) -> Template:
        if resource not in self._names:
            fail("unknown_resource", f"Unknown resource {resource!r}.")
        if source not in {"name", "location"}:
            fail("invalid_source", "Source must be 'name' or 'location'.")
        if source == "location" and resource not in self._locations:
            fail("missing_location", f"No location defined for {resource!r}.")
        return (self._names if source == "name" else self._locations)[resource]

    def validate(self, text: str, resource: str, *, source: str = "name") -> Validation:
        return self._template(resource, source).validate(text, resource, source)

    def inspect(self, text: str, *, source: str = "name") -> Inspection:
        if source not in {"name", "location"}:
            fail("invalid_source", "Source must be 'name' or 'location'.")
        templates = self._names if source == "name" else self._locations
        results = [template.validate(text, name, source) for name, template in templates.items()]
        matches = tuple(result for result in results if result.valid)
        candidates = tuple(
            result
            for result in results
            if not result.valid and all(d.code != "pattern_mismatch" for d in result.diagnostics)
        )
        status = "valid" if len(matches) == 1 else "ambiguous" if matches else "invalid"
        return Inspection(status, matches, candidates)

    def parse(self, text: str, resource: str | None = None, *, source: str = "name") -> Resource:
        if resource is not None:
            result = self.validate(text, resource, source=source)
            if not result.valid:
                raise NameSpecError(list(result.diagnostics))
        else:
            inspection = self.inspect(text, source=source)
            if inspection.status == "ambiguous":
                fail(
                    "ambiguous_resource",
                    "Input matches multiple resources; specify one.",
                    actual=[match.resource for match in inspection.matches],
                )
            if not inspection.matches:
                fail("no_match", "No valid resource match. Use inspect() to see candidates.")
            result = inspection.matches[0]
        return Resource(self, result.resource, result.fields)

    def format(self, resource: str, /, **fields: Any) -> str:
        return self._template(resource, "name").format(fields)

    def locate(self, resource: str, /, **fields: Any) -> str:
        """Derive a location; this neither checks existence nor touches the filesystem."""
        return self._template(resource, "location").format(fields)

    def register_reader(self, name: str, reader: Callable[[Path], Any]) -> None:
        """Handlers are registered by the host, never imported or executed from a schema."""
        if not callable(reader):
            raise TypeError("reader must be callable")
        self._readers[name] = reader

    def check_examples(self) -> list[Diagnostic]:
        """Run exact expected-field and expected-error assertions in the rule document."""
        failures: list[Diagnostic] = []
        for index, example in enumerate(self.definition.examples, 1):
            result = self.validate(example.input, example.resource)
            if example.error_code:
                passed = any(d.code == example.error_code for d in result.diagnostics)
                expected = example.error_code
                actual = [d.code for d in result.diagnostics]
            else:
                # Avoid Python's loose numeric equality hiding a type error in the contract.
                passed = (
                    result.valid
                    and result.fields == example.expected
                    and all(
                        type(result.fields[key]) is type(value)
                        for key, value in example.expected.items()
                    )
                )
                expected, actual = example.expected, result.fields
            if not passed:
                failures.append(
                    Diagnostic(
                        "example_failed",
                        f"Example {index} for {example.resource!r} failed.",
                        expected=expected,
                        actual=actual,
                    )
                )
        return failures

    def samples(self, resource: str, *, limit: int = 10, **overrides: Any) -> Iterator[str]:
        """Generate bounded examples from enums, integer minima, and authored text examples.

        Regex inversion is deliberately not inferred. Supply samples or explicit values.
        """
        if limit < 0:
            raise ValueError("limit must be nonnegative")
        names = list(dict.fromkeys(self._template(resource, "name").names))
        choices: list[tuple[Any, ...]] = []
        for name in names:
            spec = self.definition.fields[name]
            if name in overrides:
                values = (overrides[name],)
            elif spec.kind == "integer":
                values = (spec.minimum, spec.minimum + 1)
            else:
                values = spec.choices or spec.samples
            if not values:
                fail("missing_sample", f"Provide examples or a value for {name!r}.", field=name)
            choices.append(values)
        for values in islice(product(*choices), limit):
            yield self.format(resource, **dict(zip(names, values, strict=True)))


class Resource:
    """Successfully parsed metadata, with explicit operations on the described resource."""

    def __init__(self, catalog: Catalog, kind: str, fields: dict[str, str | int]):
        self.catalog = catalog
        self.kind = kind
        self._fields = dict(fields)

    @property
    def fields(self) -> dict[str, str | int]:
        return dict(self._fields)

    @property
    def name(self) -> str:
        return self.catalog.format(self.kind, **self._fields)

    def locate(self, **context: Any) -> str:
        for name, value in context.items():
            if name in self._fields and (
                value != self._fields[name] or type(value) is not type(self._fields[name])
            ):
                fail(
                    "context_conflict", f"Context conflicts with parsed field {name!r}.", field=name
                )
        return self.catalog.locate(self.kind, **{**context, **self._fields})

    @property
    def reader_id(self) -> str:
        spec = self.catalog.definition.resources[self.kind]
        if spec.reader_field is None:
            fail("missing_reader", f"No reader selection defined for {self.kind!r}.")
        return self.catalog.definition.readers[self._fields[spec.reader_field]]

    def read(self, **context: Any) -> Any:
        """Resolve the path and invoke the host reader. File errors propagate from the reader."""
        reader_id = self.reader_id
        reader = self.catalog._readers.get(reader_id)
        if reader is None:
            fail("unavailable_reader", f"Register a handler for {reader_id!r} first.")
        return reader(Path(self.locate(**context)))
