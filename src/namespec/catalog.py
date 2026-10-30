"""Public naming, discovery, location, and explicit reader operations."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator, Mapping
from dataclasses import replace
from fnmatch import fnmatchcase
from functools import cache
from pathlib import Path, PurePath
from typing import Any, Literal, TypeVar

from .models import (
    Definition,
    Diagnostic,
    ExampleResult,
    ExampleSpec,
    FieldSpec,
    Inspection,
    NameSpecError,
    ResourceSpec,
    Validation,
    fail,
    located,
)
from .parser import compile_definition
from .policies import check_filesystem_policy, filesystem_diagnostics
from .template import Template, field_value, parse_parts, spelling

ResourceT = TypeVar("ResourceT", bound="Resource")


class Catalog:
    """Load naming rules, parse names or paths, and derive related resources.

    Start with Catalog.from_file(...) and catalog.parse(value).
    The resources, fields and roots attributes expose the available rules.
    """

    def __init__(
        self, definition: Definition, *, strict: bool = False, filesystem: str | None = None
    ):
        check_filesystem_policy(filesystem)
        self.strict = strict
        self.filesystem = filesystem
        self.definition = definition
        roots = {name: self.normalize(path) for name, path in definition.roots.items()}
        seen_roots: set[str] = set()
        for name, path in roots.items():
            if path in seen_roots:
                fail(
                    "duplicate_root",
                    "Root prefixes must remain distinct after normalization.",
                    span=definition.spans.get(("roots", name)),
                )
            seen_roots.add(path)
        # Compile the same canonical spelling that validation reads and generation emits.
        self.definition = definition = replace(
            definition,
            roots=roots,
            resources={
                name: replace(spec, location=self.normalize(spec.location))
                if spec.location is not None
                else spec
                for name, spec in definition.resources.items()
            },
        )
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
                    self._composite(spec.name)
        for name, spec in definition.resources.items():
            template = None
            if spec.template is not None:
                with located(spans.get(("resource", name, "name"))):
                    template = Template(
                        spec.template, definition.fields, composite_cache=self._composites
                    )
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
        expanded: list[str] = []
        for literal, field, formatting, conversion in parse_parts(spec.location):
            # Formatter decodes escaped braces. Re-escape literals before the next parse.
            expanded.append(literal.replace("{", "{{").replace("}", "}}"))
            if field is None:
                continue
            if formatting or conversion:
                fail("invalid_template", "Put formatting rules in field definitions.")
            if field == "name":
                if template is None:
                    fail(
                        "invalid_template",
                        f"Folder resource {name!r} has no filename to put in {{name}}.",
                    )
                expanded.append(spec.template)
            else:
                expanded.append("{" + field + "}")
        location = Template(
            self.normalize("".join(expanded)),
            self.definition.fields,
            roots=self.definition.roots,
            composite_cache=self._composites,
        )
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
    def from_string(
        cls, source: str, *, strict: bool = False, filesystem: str | None = None
    ) -> Catalog:
        definition = compile_definition(source)
        try:
            return cls(definition, strict=strict, filesystem=filesystem)
        except NameSpecError as exc:
            raise NameSpecError(exc.diagnostics, source) from None

    @classmethod
    def from_file(
        cls, path: str | os.PathLike[str], *, strict: bool = False, filesystem: str | None = None
    ) -> Catalog:
        return cls.from_string(
            Path(path).read_text(encoding="utf-8"), strict=strict, filesystem=filesystem
        )

    @classmethod
    def from_env(
        cls,
        variable: str = "NAMESPEC_RULES",
        default: str | os.PathLike[str] | None = None,
        *,
        strict: bool = False,
        filesystem: str | None = None,
    ) -> Catalog:
        """The catalog an environment variable points at; memoized, see ``load_rules``."""
        return load_rules(variable, default, strict=strict, filesystem=filesystem)

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
                self.definition.fields[name].template,
                self.definition.fields,
                composite_cache=self._composites,
            )
        return self._composites[name]

    @property
    def resources(self) -> Mapping[str, ResourceSpec]:
        """Read-only resource definitions, keyed by kind."""
        return self.definition.resources

    @property
    def fields(self) -> Mapping[str, FieldSpec]:
        """Read-only field definitions, including choices, bounds and samples."""
        return self.definition.fields

    @property
    def roots(self) -> dict[str, str]:
        """Declared root names mapped to their literal path prefixes."""
        return dict(self.definition.roots)

    def root_name(self, value: str | os.PathLike[str]) -> str:
        """The declared name of a root, given either its name or its path."""
        value = as_text(value)
        if value in self.definition.roots:
            return value
        value = self.normalize(value)
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
        if (
            drive
            and len(text) >= 2
            and text[1] == ":"
            and text[0] in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        ):
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

    def validate(
        self,
        text: str | os.PathLike[str],
        resource: str,
        *,
        source: Literal["auto", "name", "location"] = "auto",
    ) -> Validation:
        """Validate one resource; ``source="auto"`` tries its name and location templates.

        Use ``source="name"`` for a filename input, or ``source="location"`` to
        require the declared folder layout. ``inspect()`` shows competing readings
        when validation reports ambiguity.
        """
        text = as_text(text)
        results = self._validation_results(text, resource, source)
        matches = self._distinct_matches(results)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return self._source_ambiguity(text, resource, matches)
        if len(results) == 1:
            return results[0]
        candidates = [result for result in results if self._is_candidate(result)]
        if len(candidates) == 1:
            return candidates[0]
        if candidates:
            # Neither source is valid and both structures fit. Keep their evidence rather
            # than assigning an arbitrary source or returning fields they disagree about.
            common = {
                name: value
                for name, value in candidates[0].fields.items()
                if all(result.fields.get(name) == value for result in candidates[1:])
            }
            diagnostics = tuple(
                replace(item, message=f"{result.source}: {item.message}")
                for result in candidates
                for item in result.diagnostics
            )
            return Validation(resource, text, common, diagnostics, "auto")
        additional = []
        for result in results:
            for item in result.diagnostics:
                if item.code != "pattern_mismatch" and item not in additional:
                    additional.append(item)
        return Validation(
            resource,
            text,
            {},
            (
                Diagnostic(
                    "pattern_mismatch",
                    "Input fits neither the name nor the location template.",
                    expected={
                        result.source: self._template(resource, result.source).text
                        for result in results
                    },
                    actual=text,
                ),
                *additional,
            ),
            "auto",
        )

    def _validation_results(self, text: str, resource: str | None, source: str) -> list[Validation]:
        if resource is not None and resource not in self.definition.resources:
            fail("unknown_resource", f"Unknown resource {resource!r}.")
        if source not in {"auto", "name", "location"}:
            fail("invalid_source", "Source must be 'auto', 'name' or 'location'.")
        if resource is not None and source != "auto":
            template = self._template(resource, source)
            return [
                self._filesystem_result(
                    template.validate(self.normalize(text, source), resource, source)
                )
            ]
        results = []
        for selected in ("name", "location") if source == "auto" else (source,):
            normalized = self.normalize(text, selected)
            templates = self._names if selected == "name" else self._locations
            for kind, template in templates.items():
                if resource is None or kind == resource:
                    results.append(
                        self._filesystem_result(template.validate(normalized, kind, selected))
                    )
        return results

    @staticmethod
    def _distinct_matches(results: list[Validation]) -> tuple[Validation, ...]:
        matches: list[Validation] = []
        for result in results:
            if not result.valid:
                continue
            for index, previous in enumerate(matches):
                if result.resource == previous.resource and result.fields == previous.fields:
                    if result.source == "location":
                        matches[index] = result
                    break
            else:
                matches.append(result)
        return tuple(matches)

    @staticmethod
    def _is_candidate(result: Validation) -> bool:
        return not result.valid and all(
            item.code != "pattern_mismatch" for item in result.diagnostics
        )

    @staticmethod
    def _source_ambiguity(text: str, resource: str, matches: tuple[Validation, ...]) -> Validation:
        return Validation(
            resource,
            text,
            {},
            (
                Diagnostic(
                    "ambiguous_source",
                    f"Input has different name and location readings for {resource!r}; "
                    "specify source.",
                    actual=[
                        {"source": result.source, "fields": result.fields} for result in matches
                    ],
                ),
            ),
            "auto",
        )

    def _filesystem_result(self, result: Validation) -> Validation:
        diagnostics = filesystem_diagnostics(result.input, self.filesystem, source=result.source)
        return (
            replace(result, diagnostics=(*result.diagnostics, *diagnostics))
            if diagnostics
            else result
        )

    def inspect(
        self,
        text: str | os.PathLike[str],
        *,
        source: Literal["auto", "name", "location"] = "auto",
    ) -> Inspection:
        """List matching names and locations by default, retaining competing readings.

        ``source="auto"`` helps explain ambiguity before choosing a resource or source.
        Use ``source="name"`` for a filename input, or ``source="location"`` to
        require a declared folder layout.
        """
        results = self._validation_results(as_text(text), None, source)
        matches = self._distinct_matches(results)
        candidates = tuple(result for result in results if self._is_candidate(result))
        status = "valid" if len(matches) == 1 else "ambiguous" if matches else "invalid"
        return Inspection(status, matches, candidates)

    def parse(
        self,
        text: str | os.PathLike[str],
        resource: str | None = None,
        *,
        source: Literal["auto", "name", "location"] = "auto",
    ) -> Resource:
        """Parse one distinct reading; ``source="auto"`` tries names and locations.

        Use ``source="name"`` for a filename input, or ``source="location"`` to
        require the declared folder layout. If parsing is ambiguous, ``inspect()``
        shows the competing matches and their fields.
        """
        text = as_text(text)
        if resource is not None:
            result = self.validate(text, resource, source=source)
            if not result.valid:
                raise NameSpecError(list(result.diagnostics))
        else:
            inspection = self.inspect(text, source=source)
            if inspection.status == "ambiguous":
                kinds = list(dict.fromkeys(match.resource for match in inspection.matches))
                if len(kinds) == 1:
                    result = self._source_ambiguity(text, kinds[0], inspection.matches)
                    raise NameSpecError(list(result.diagnostics))
                fail(
                    "ambiguous_resource",
                    "Input matches multiple resources; specify one.",
                    actual=kinds,
                )
            if not inspection.matches:
                fail("no_match", "No valid resource match. Use inspect() to see candidates.")
            result = inspection.matches[0]
        resource = self.resource_class(result.resource)(self, result.resource, result.fields)
        resource._source = result.source
        return resource

    def format(
        self, resource: str, base: Mapping[str, Any] | None = None, /, **overrides: Any
    ) -> str:
        """Render a name from a base mapping plus overrides; overrides win, extras are ignored."""
        return self._render(resource, "name", _merge(base, overrides))

    def locate(
        self, resource: str, base: Mapping[str, Any] | None = None, /, **overrides: Any
    ) -> Path:
        """Derive a native Path without checking existence or touching the filesystem."""
        return Path(self._render(resource, "location", _merge(base, overrides)))

    def _location_values(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Resolve root labels and path objects before comparing or formatting context."""
        values = dict(values)
        root = values.get("root")
        if isinstance(root, (str, os.PathLike)):
            root = as_text(root)
            values["root"] = self.definition.roots.get(root, self.normalize(root))
        return values

    def _render(
        self, resource: str, source: str, values: Mapping[str, Any], *, strict: bool | None = None
    ) -> str:
        values = self._location_values(values) if source == "location" else dict(values)
        output = self._template(resource, source).format(
            values, strict=self.strict if strict is None else strict
        )
        diagnostics = filesystem_diagnostics(output, self.filesystem, source=source)
        if diagnostics:
            raise NameSpecError(list(diagnostics))
        return output

    def register_reader(self, name: str, reader: Callable[[Path], Any]) -> None:
        """Handlers are registered by the host, never imported or executed from a schema."""
        if not callable(reader):
            raise TypeError("reader must be callable")
        self._readers[name] = reader

    def resource(self, *kinds: str) -> Callable[[type[ResourceT]], type[ResourceT]]:
        """Decorate a ``Resource`` subclass so parses of these kinds return instances of it.

        ``kinds`` are resource names or ``fnmatch`` patterns. Rule documents stay data; the
        behavior a studio wants on a parsed path lives on these ordinary Python classes.
        """

        def bind(cls: type[ResourceT]) -> type[ResourceT]:
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
        if limit == 0:
            return
        supplied = template.resolve_values(overrides)
        for name, value in overrides.items():
            if name in template.composites and value is None:
                for part in self._composite(name).produced:
                    supplied.setdefault(part, None)
        names = list(dict.fromkeys(template.names))
        # Groups that share a field must agree on presence, including repeated groups.
        components: list[set[str]] = []
        for group in template.groups:
            members = set(group.names)
            for existing in components[:]:
                if existing & members:
                    members.update(existing)
                    components.remove(existing)
            components.append(members)
        component_of = {name: index for index, group in enumerate(components) for name in group}
        presence: dict[int, bool] = {}
        for index, group in enumerate(components):
            if group & template.required or any(supplied.get(name) is not None for name in group):
                presence[index] = True
            elif any(name in supplied for name in group):
                presence[index] = False
        choices: dict[str, tuple[Any, ...]] = {}
        for name in names:
            spec = self.definition.fields[name]
            if name in supplied:
                values: tuple[Any, ...] = (supplied[name],)
            elif spec.kind == "integer":
                values = (spec.minimum, spec.minimum + 1)
                if spec.maximum is not None:
                    values = tuple(value for value in values if value <= spec.maximum)
            else:
                values = spec.choices or spec.samples
            if name in template.optional and name not in supplied:
                values = (None, *values)
            choices[name] = values

        def combinations(index: int, selected: dict[str, Any], active: dict[int, bool]):
            if index == len(names):
                yield selected
                return
            name = names[index]
            component = component_of.get(name)
            required = active.get(component) if component is not None else True
            values = choices[name]
            if required is False:
                values = (None,)
            elif required is True:
                values = tuple(value for value in values if value is not None)
            if not values:
                if component is not None and component not in presence:
                    return  # This optional presence has no authored samples to generate.
                code = "missing_field" if name in supplied else "missing_sample"
                fail(code, f"Provide examples or a value for {name!r}.", field=name)
            for value in values:
                next_active = active
                if component is not None and component not in active:
                    next_active = {**active, component: value is not None}
                yield from combinations(index + 1, {**selected, name: value}, next_active)

        for index, values in enumerate(combinations(0, supplied, presence)):
            yield self.format(resource, values)
            if index + 1 == limit:
                return


def load_rules(
    variable: str = "NAMESPEC_RULES",
    default: str | os.PathLike[str] | None = None,
    *,
    strict: bool = False,
    filesystem: str | None = None,
) -> Catalog:
    """Load the rule file an environment variable names, or ``default``. Memoized per process.

    DCC launchers set the variable so every tool reads the same studio file. Call
    ``load_rules.cache_clear()`` if the variable changes mid-process. Classes bound on the
    returned catalog are shared by everything in the process that loads it this way.
    """
    return _load_rules(variable, default, strict, filesystem)


@cache
def _load_rules(
    variable: str, default: str | os.PathLike[str] | None, strict: bool, filesystem: str | None
) -> Catalog:
    path = os.environ.get(variable, "").strip() or default
    if not path:
        fail("missing_rules", f"Set {variable} to a .names file or pass a default path.")
    return Catalog.from_file(path, strict=strict, filesystem=filesystem)


load_rules.cache_clear = _load_rules.cache_clear
load_rules.cache_info = _load_rules.cache_info


def as_text(value: Any) -> str:
    """Accept a string or a path object. A ``PurePath`` is read in POSIX form."""
    if isinstance(value, PurePath):
        return value.as_posix()
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
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


class Resource(Mapping[str, str | int]):
    """A parsed name or path with discoverable fields and lazy path operations.

    Subclass it and bind the subclass with ``Catalog.resource`` to put studio behavior on
    parsed paths. Keep ``__init__`` as it is; parsing constructs instances. Access values
    with resource["version"] or resource.get("tag"); use path for pathlib operations
    and with_context, replace or related for derived resources.
    """

    def __init__(self, catalog: Catalog, kind: str, fields: dict[str, str | int]):
        self.catalog = catalog
        self.kind = kind
        self._fields = dict(fields)
        self._source = "name"

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.kind!r}, {self._fields!r}, source={self.source!r})"

    def __getitem__(self, key: str) -> str | int:
        """Get a parsed field; unknown or absent fields raise KeyError."""
        return self._fields[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._fields)

    def __len__(self) -> int:
        return len(self._fields)

    def __fspath__(self) -> str:
        """Allow Path(resource) and other os.PathLike consumers."""
        return os.fspath(self.path)

    @property
    def source(self) -> str:
        """The matched template: 'name' or 'location'."""
        return self._source

    @property
    def definition(self) -> ResourceSpec:
        """The read-only definition of this resource kind."""
        return self.catalog.resources[self.kind]

    @property
    def fields(self) -> dict[str, str | int]:
        return dict(self._fields)

    @property
    def metadata(self) -> dict[str, Any]:
        """The resource's ``meta`` block: data for hosts, ignored by matching."""
        return dict(self.definition.metadata)

    @property
    def name(self) -> str:
        """The formatted filename. Folder resources have no filename template."""
        return self.catalog.format(self.kind, self._fields)

    @property
    def path(self) -> Path:
        """The parsed name or location as a native Path, computed without filesystem I/O.

        A basename stays relative. Use with_context(...) to obtain a resource at its
        declared location. Path's parent, suffix, stem and I/O methods are then available.
        """
        return Path(self.catalog._render(self.kind, self.source, self._fields))

    @property
    def root(self) -> Path | None:
        """The parsed root prefix as a Path, or None when the input has no root."""
        value = self._fields.get("root")
        return Path(str(value)) if value is not None else None

    @property
    def root_name(self) -> str | None:
        """The declared root label, or None when the input has no root."""
        value = self._fields.get("root")
        return self.catalog.root_name(str(value)) if value is not None else None

    @property
    def missing_context(self) -> tuple[str, ...]:
        """Field names still needed to build the declared location, in template order.

        A name-only definition has no location context and returns an empty tuple.
        Optional groups contribute fields only once one of their members is supplied.
        """
        if self.definition.location is None:
            return ()
        template = self.catalog._template(self.kind, "location")
        values = template.resolve_values(self._fields)
        wanted = set(template.required)
        if template.has_root:
            wanted.add("root")
        for group in template.groups:
            if any(values.get(name) is not None for name in group.names):
                wanted.update(group.names)
        return tuple(
            name for name in template.produced if name in wanted and values.get(name) is None
        )

    def replace(self: ResourceT, **changes: Any) -> ResourceT:
        """Return a validated copy, recomputing composites affected by the changed fields.

        A composite replacement supplies its parts; a part replacement invalidates its old
        composites. Explicitly supplied whole/part conflicts still raise. ``None`` removes
        an optional value. The original resource and its bound class are preserved.
        """
        template = self.catalog._template(self.kind, self._source)
        unknown = changes.keys() - set(template.produced)
        if unknown:
            name = sorted(unknown)[0]
            fail("unknown_field", f"{name!r} is not a field of this resource.", field=name)
        values: dict[str, Any] = self.fields
        affected = set(changes)
        for name in changes:
            if name in template.composites:
                composite = self.catalog._composite(name)
                affected.update(composite.names)
                for part in composite.produced:
                    values.pop(part, None)
        for name in template.composites:
            if affected.intersection(self.catalog._composite(name).names):
                values.pop(name, None)
        values.update(changes)
        text = self.catalog._render(self.kind, self._source, values, strict=True)
        result = self.catalog.validate(text, self.kind, source=self._source)
        if not result.valid:
            raise NameSpecError(list(result.diagnostics))
        updated = type(self)(self.catalog, self.kind, result.fields)
        updated._source = self._source
        return updated

    def _location_context(self, context: Mapping[str, Any]) -> dict[str, Any]:
        context = self.catalog._location_values(context)
        for name, value in context.items():
            if name in self._fields and (
                value != self._fields[name] or type(value) is not type(self._fields[name])
            ):
                fail(
                    "context_conflict", f"Context conflicts with parsed field {name!r}.", field=name
                )
        return {**context, **self._fields}

    def locate(self, **context: Any) -> Path:
        """Build a location Path, supplying missing context without changing this resource."""
        return self.catalog.locate(self.kind, self._location_context(context))

    def with_context(self: ResourceT, **context: Any) -> ResourceT:
        """Return a located copy with complete context, keeping this resource unchanged.

        Use missing_context to see required fields. Context may fill location fields but
        cannot overwrite parsed values. The resulting fields must survive a roundtrip.
        """
        template = self.catalog._template(self.kind, "location")
        unknown = context.keys() - set(template.produced)
        if unknown:
            name = sorted(unknown)[0]
            fail("unknown_field", f"{name!r} is not a location field of this resource.", field=name)
        text = self.catalog._render(
            self.kind, "location", self._location_context(context), strict=True
        )
        result = self.catalog.validate(text, self.kind, source="location")
        if not result.valid:
            raise NameSpecError(list(result.diagnostics))
        updated = type(self)(self.catalog, self.kind, result.fields)
        updated._source = "location"
        return updated

    def related(self, kind: str, /, **overrides: Any) -> Resource:
        """Derive another resource using these fields, with explicit overrides.

        Prefer the target's location when defined, otherwise its name. This builds and
        validates a resource; it does not search for files or invoke a reader.
        """
        if kind not in self.catalog.resources:
            fail("unknown_resource", f"Unknown resource {kind!r}.")
        source = "location" if self.catalog.resources[kind].location is not None else "name"
        text = self.catalog._render(kind, source, _merge(self._fields, overrides), strict=True)
        return self.catalog.parse(text, kind, source=source)

    @property
    def reader_id(self) -> str:
        spec = self.catalog.definition.resources[self.kind]
        if spec.reader_field is None:
            fail("missing_reader", f"No reader selection defined for {self.kind!r}.")
        if spec.reader_field not in self._fields:
            fail(
                "missing_reader",
                f"Reader selection requires absent field {spec.reader_field!r}.",
                field=spec.reader_field,
            )
        return self.catalog.definition.readers[self._fields[spec.reader_field]]

    def read(self, **context: Any) -> Any:
        """Resolve the path and invoke the host reader. File errors propagate from the reader."""
        reader_id = self.reader_id
        reader = self.catalog._readers.get(reader_id)
        if reader is None:
            fail("unavailable_reader", f"Register a handler for {reader_id!r} first.")
        return reader(self.locate(**context))
