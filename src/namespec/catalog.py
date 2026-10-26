"""Public naming, discovery, location, and explicit reader operations."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator, Mapping
from fnmatch import fnmatchcase
from functools import cache
from itertools import islice, product
from pathlib import Path, PurePath
from typing import Any

from .models import (
    Definition,
    Diagnostic,
    ExampleResult,
    ExampleSpec,
    Inspection,
    NameSpecError,
    Validation,
    fail,
    located,
)
from .parser import compile_definition
from .template import Template, field_value, spelling


class Catalog:
    def __init__(self, definition: Definition):
        self.definition = definition
        self._names: dict[str, Template] = {}
        self._locations: dict[str, Template] = {}
        self._readers: dict[str, Callable[[Path], Any]] = {}
        self._classes: dict[str, type[Resource]] = {}
        self._composites: dict[str, Template] = {}
        spans = definition.spans
        for spec in definition.fields.values():
            if spec.kind == "composite":
                # Surfaces unknown parts, cycles and ambiguous boundaries for unused composites too.
                with located(spans.get(("field", spec.name))):
                    Template(spec.template, definition.fields)
        for name, spec in definition.resources.items():
            template = None
            if spec.template is not None:
                with located(spans.get(("resource", name, "name"))):
                    template = Template(spec.template, definition.fields)
                self._names[name] = template
            if spec.location:
                with located(spans.get(("resource", name, "location"))):
                    self._locations[name] = self._location(name, template)
            if spec.reader_field:
                with located(spans.get(("resource", name, "reader"))):
                    if template is None:
                        fail("invalid_reader", f"Folder resource {name!r} cannot select a reader.")
                    self._check_reader(name, spec.reader_field, template)
        for index, example in enumerate(definition.examples):
            span = spans.get(("example", index, "input"))
            if example.source == "location" and example.resource not in self._locations:
                fail(
                    "missing_location",
                    f"A location example needs a location on resource {example.resource!r}.",
                    span=span,
                )
            if example.source == "name" and example.resource not in self._names:
                fail(
                    "missing_name",
                    f"Resource {example.resource!r} has no name; use a location example.",
                    span=span,
                )

    def _location(self, name: str, template: Template | None) -> Template:
        spec = self.definition.resources[name]
        if template is None:
            if "{name}" in spec.location:
                fail(
                    "invalid_template",
                    f"Folder resource {name!r} has no filename to put in {{name}}.",
                )
            expanded = spec.location
        else:
            # Expand the filename into field slots, retaining repeated-value checks.
            expanded = spec.location.replace("{name}", spec.template)
        location = Template(expanded, self.definition.fields, roots=self.definition.roots)
        if template is not None and not set(template.names).issubset(location.names):
            fail("incomplete_location", f"Location for {name!r} must include its name fields.")
        return location

    def _check_reader(self, name: str, reader_field: str, template: Template) -> None:
        if reader_field not in template.names:
            fail("unknown_field", f"Reader field {reader_field!r} is not in the name of {name!r}.")
        field = self.definition.fields[reader_field]
        if field.kind != "enum":
            fail("invalid_reader", "Reader selection requires an enum field.")
        missing = set(field.choices) - self.definition.readers.keys()
        if missing:
            fail("missing_reader_mapping", f"Missing reader mappings: {sorted(missing)}.")

    @classmethod
    def from_string(cls, source: str) -> Catalog:
        definition = compile_definition(source)
        try:
            return cls(definition)
        except NameSpecError as exc:
            raise NameSpecError(exc.diagnostics, source) from None

    @classmethod
    def from_file(cls, path: str | os.PathLike[str]) -> Catalog:
        return cls.from_string(Path(path).read_text(encoding="utf-8"))

    @classmethod
    def from_env(
        cls, variable: str = "NAMESPEC_RULES", default: str | os.PathLike[str] | None = None
    ) -> Catalog:
        """The catalog an environment variable points at; memoized, see ``load_rules``."""
        return load_rules(variable, default)

    def validate_field(self, name: str, text: Any) -> Validation:
        """Check one value against one field's rule, with no template around it."""
        spec = self.definition.fields.get(name)
        if spec is None:
            fail("unknown_field", f"Unknown field {name!r}.", field=name)
        text = as_text(text)
        if spec.kind == "composite":
            return self._composite(name).validate(text, name, "field")
        try:
            value = field_value(spec, text, parsing=True)
        except NameSpecError as exc:
            return Validation(name, text, {}, tuple(exc.diagnostics), "field")
        return Validation(name, text, {name: value}, (), "field")

    def format_field(self, name: str, value: Any) -> str:
        """Spell one value as a name would contain it: 6 becomes "006" for a padded field."""
        spec = self.definition.fields.get(name)
        if spec is None:
            fail("unknown_field", f"Unknown field {name!r}.", field=name)
        if spec.kind == "composite":
            result = self.validate_field(name, value)
            if not result.valid:
                raise NameSpecError(list(result.diagnostics))
            return result.input
        return spelling(spec, field_value(spec, value, parsing=False))

    def _composite(self, name: str) -> Template:
        if name not in self._composites:
            self._composites[name] = Template(
                self.definition.fields[name].template, self.definition.fields
            )
        return self._composites[name]

    @property
    def roots(self) -> dict[str, str]:
        """Declared root names mapped to their literal path prefixes."""
        return dict(self.definition.roots)

    def root_name(self, value: str) -> str:
        """The declared name of a root, given either its name or its path."""
        if value in self.definition.roots:
            return value
        for name, path in self.definition.roots.items():
            if path == value:
                return name
        fail("unknown_root", f"{value!r} is not a declared root.", field="root", actual=value)

    def normalize(self, text: str | os.PathLike[str], source: str = "location") -> str:
        """Apply the document's ``normalize`` block to a location. Names are never changed.

        A ``PurePath`` is taken in POSIX form first. Both options preserve length, so
        diagnostic spans are valid for the original text too.
        """
        text = as_text(text)
        if source != "location":
            return text
        options = self.definition.normalize
        if options.get("slashes") == "forward":
            text = text.replace("\\", "/")
        drive = options.get("drive")
        if drive and len(text) >= 2 and text[1] == ":" and text[0].isalpha():
            first = text[0].upper() if drive == "upper" else text[0].lower()
            text = first + text[1:]
        return text

    def _template(self, resource: str, source: str) -> Template:
        if resource not in self.definition.resources:
            fail("unknown_resource", f"Unknown resource {resource!r}.")
        if source not in {"name", "location"}:
            fail("invalid_source", "Source must be 'name' or 'location'.")
        if source == "location":
            if resource not in self._locations:
                fail("missing_location", f"No location defined for {resource!r}.")
            return self._locations[resource]
        if resource not in self._names:
            fail("missing_name", f"{resource!r} is a folder resource; use source='location'.")
        return self._names[resource]

    def validate(self, text: str, resource: str, *, source: str = "name") -> Validation:
        template = self._template(resource, source)
        return template.validate(self.normalize(text, source), resource, source)

    def inspect(self, text: str, *, source: str = "name") -> Inspection:
        if source not in {"name", "location"}:
            fail("invalid_source", "Source must be 'name' or 'location'.")
        text = self.normalize(text, source)
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
        return self.resource_class(result.resource)(self, result.resource, result.fields)

    def format(
        self, resource: str, base: Mapping[str, Any] | None = None, /, **overrides: Any
    ) -> str:
        """Render a name from a base mapping plus overrides; overrides win, extras are ignored."""
        return self._template(resource, "name").format(_merge(base, overrides))

    def locate(
        self, resource: str, base: Mapping[str, Any] | None = None, /, **overrides: Any
    ) -> str:
        """Derive a location; this neither checks existence nor touches the filesystem."""
        return self._template(resource, "location").format(_merge(base, overrides))

    def register_reader(self, name: str, reader: Callable[[Path], Any]) -> None:
        """Handlers are registered by the host, never imported or executed from a schema."""
        if not callable(reader):
            raise TypeError("reader must be callable")
        self._readers[name] = reader

    def resource(self, *kinds: str) -> Callable[[type[Resource]], type[Resource]]:
        """Decorate a ``Resource`` subclass so parses of these kinds return instances of it.

        ``kinds`` are resource names or ``fnmatch`` patterns. Rule documents stay data; the
        behavior a studio wants on a parsed path lives on these ordinary Python classes.
        """

        def bind(cls: type[Resource]) -> type[Resource]:
            self.bind(cls, *kinds)
            return cls

        return bind

    def bind(self, cls: type[Resource], *kinds: str) -> None:
        if not (isinstance(cls, type) and issubclass(cls, Resource)):
            raise TypeError("bind a subclass of Resource")
        if not kinds:
            raise TypeError("name at least one resource or pattern")
        matched: set[str] = set()
        for pattern in kinds:
            if any(character in pattern for character in "*?["):
                matched.update(
                    kind for kind in self.definition.resources if fnmatchcase(kind, pattern)
                )
            elif pattern in self.definition.resources:
                matched.add(pattern)
            else:
                fail("unknown_resource", f"Unknown resource {pattern!r}.", actual=pattern)
        for kind in sorted(matched):
            current = self._classes.get(kind)
            if current is not None and current is not cls:
                fail(
                    "duplicate_binding",
                    f"{kind!r} is already bound to {current.__name__}.",
                    expected=current.__name__,
                    actual=cls.__name__,
                )
        for kind in matched:
            self._classes[kind] = cls

    def resource_class(self, kind: str) -> type[Resource]:
        """The class a parse of this kind returns: a bound subclass, or ``Resource`` itself."""
        if kind not in self.definition.resources:
            fail("unknown_resource", f"Unknown resource {kind!r}.")
        return self._classes.get(kind, Resource)

    def run_examples(self) -> list[ExampleResult]:
        """Run every inline example and rejection. Each failure says what differed and where."""
        spans = self.definition.spans
        return [
            ExampleResult(
                example, spans.get(("example", index)), tuple(self._failures(index, example))
            )
            for index, example in enumerate(self.definition.examples)
        ]

    def check_examples(self) -> list[Diagnostic]:
        """The failures from ``run_examples``, flattened; empty when every example holds."""
        return [failure for result in self.run_examples() for failure in result.failures]

    def _failures(self, index: int, example: ExampleSpec) -> Iterator[Diagnostic]:
        def failed(message: str, *at: str, **details: Any) -> Diagnostic:
            span = self.definition.spans.get(("example", index, *at))
            return Diagnostic("example_failed", message, span=span, **details)

        result = self.validate(example.input, example.resource, source=example.source)
        codes = [item.code for item in result.diagnostics]
        reasons = " ".join(item.message for item in result.diagnostics)
        if example.error_code:
            if example.error_code in codes:
                return
            message = (
                f"Expected {example.error_code}, but this is a valid {example.resource}."
                if result.valid
                else f"Expected {example.error_code}, got {', '.join(codes)}: {reasons}"
            )
            yield failed(message, "input", expected=example.error_code, actual=codes)
            return
        if not result.valid:
            message = f"Not a valid {example.resource}: {reasons}"
            yield failed(message, "input", expected=example.expected, actual=codes)
            return
        for name, value in example.expected.items():
            if name not in result.fields:
                message = (
                    f"Expected {name} = {literal(value)}, "
                    f"but this {example.resource} has no {name}."
                )
                yield failed(message, "expect", name, field=name, expected=value)
                continue
            actual = result.fields[name]
            # Avoid Python's loose numeric equality hiding a type error in the contract.
            if actual == value and type(actual) is type(value):
                continue
            message = f"Expected {name} = {literal(value)}, got {literal(actual)}."
            if type(actual) is not type(value):
                message += (
                    f" {name} is a number, so write it without quotes."
                    if isinstance(actual, int)
                    else f" {name} is text, so quote it."
                )
            yield failed(message, "expect", name, field=name, expected=value, actual=actual)
        missing = {
            name: value for name, value in result.fields.items() if name not in example.expected
        }
        if missing:
            listed = " ".join(f"{name} = {literal(value)}" for name, value in missing.items())
            yield failed(f"Missing from expect: {listed}", "expect", actual=missing)

    def samples(self, resource: str, *, limit: int = 10, **overrides: Any) -> Iterator[str]:
        """Generate bounded examples from enums, integer minima, and authored text examples.

        Optional groups appear both absent and present. Regex inversion is deliberately not
        inferred: supply samples or explicit values.
        """
        if limit < 0:
            raise ValueError("limit must be nonnegative")
        template = self._template(resource, "name")
        names = list(dict.fromkeys(template.names))
        choices: list[tuple[Any, ...]] = []
        for name in names:
            spec = self.definition.fields[name]
            if name in overrides:
                values: tuple[Any, ...] = (overrides[name],)
            elif spec.kind == "integer":
                values = (spec.minimum, spec.minimum + 1)
            else:
                values = spec.choices or spec.samples
            if name in template.optional and name not in overrides:
                values = (None, *values)
            if not values:
                fail("missing_sample", f"Provide examples or a value for {name!r}.", field=name)
            choices.append(values)
        for values in islice(product(*choices), limit):
            yield self.format(resource, dict(zip(names, values, strict=True)))


@cache
def load_rules(
    variable: str = "NAMESPEC_RULES", default: str | os.PathLike[str] | None = None
) -> Catalog:
    """Load the rule file an environment variable names, or ``default``. Memoized per process.

    DCC launchers set the variable so every tool reads the same studio file. Call
    ``load_rules.cache_clear()`` if the variable changes mid-process. Classes bound on the
    returned catalog are shared by everything in the process that loads it this way.
    """
    path = os.environ.get(variable, "").strip() or default
    if not path:
        fail("missing_rules", f"Set {variable} to a .names file or pass a default path.")
    return Catalog.from_file(path)


def as_text(value: Any) -> str:
    """Accept a string or a path object. A ``PurePath`` is read in POSIX form."""
    if isinstance(value, PurePath):
        return value.as_posix()
    if isinstance(value, os.PathLike):
        return os.fspath(value)
    if not isinstance(value, str):
        raise TypeError("expected a string or a path object")
    return value


def literal(value: str | int) -> str:
    """A value spelled the way a rule document writes it."""
    if isinstance(value, int):
        return str(value)
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _merge(base: Mapping[str, Any] | None, overrides: Mapping[str, Any]) -> dict[str, Any]:
    if base is None:
        return dict(overrides)
    if not isinstance(base, Mapping):
        raise TypeError("base must be a mapping of field values")
    return {**base, **overrides}


class Resource:
    """Successfully parsed metadata, with explicit operations on the described resource.

    Subclass it and bind the subclass with ``Catalog.resource`` to put studio behavior on
    parsed paths. Keep ``__init__`` as it is; parsing constructs instances.
    """

    def __init__(self, catalog: Catalog, kind: str, fields: dict[str, str | int]):
        self.catalog = catalog
        self.kind = kind
        self._fields = dict(fields)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.kind!r}, {self._fields!r})"

    @property
    def fields(self) -> dict[str, str | int]:
        return dict(self._fields)

    @property
    def metadata(self) -> dict[str, Any]:
        """The resource's ``meta`` block: data for hosts, ignored by matching."""
        return dict(self.catalog.definition.resources[self.kind].metadata)

    @property
    def name(self) -> str:
        return self.catalog.format(self.kind, self._fields)

    def locate(self, **context: Any) -> str:
        for name, value in context.items():
            if name in self._fields and (
                value != self._fields[name] or type(value) is not type(self._fields[name])
            ):
                fail(
                    "context_conflict", f"Context conflicts with parsed field {name!r}.", field=name
                )
        return self.catalog.locate(self.kind, context, **self._fields)

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
