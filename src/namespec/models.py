"""Plain data shared by the parser, runtime, and JSON output."""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from typing import Any, NoReturn

SPEC_VERSION = 1
RESERVED_FIELDS = frozenset({"name", "root"})


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    field: str | None = None
    expected: Any = None
    actual: Any = None
    span: tuple[int, int] | None = None
    composite: str | None = None


class NameSpecError(ValueError):
    """A definition or operation failed, with machine-readable diagnostics.

    ``source`` is the rule text when the failure is in it. The message then leads each
    located diagnostic with its line and column; the diagnostics keep plain messages.
    """

    def __init__(self, diagnostics: list[Diagnostic], source: str | None = None):
        self.diagnostics = diagnostics
        super().__init__("; ".join(where(source, item.span) + item.message for item in diagnostics))


def fail(code: str, message: str, **details: Any) -> NoReturn:
    raise NameSpecError([Diagnostic(code, message, **details)])


def position(source: str, offset: int) -> tuple[int, int]:
    """The 1-based line and column of an offset into rule text."""
    line_start = source.rfind("\n", 0, offset) + 1
    return source.count("\n", 0, offset) + 1, offset - line_start + 1


def where(source: str | None, span: tuple[int, int] | None) -> str:
    if source is None or span is None:
        return ""
    line, column = position(source, span[0])
    return f"line {line}, column {column}: "


@contextmanager
def located(span: tuple[int, int] | None) -> Iterator[None]:
    """Point definition errors raised inside at ``span`` unless they already have one."""
    try:
        yield
    except NameSpecError as exc:
        if span is None:
            raise
        raise NameSpecError(
            [item if item.span else replace(item, span=span) for item in exc.diagnostics]
        ) from None


@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: str
    pattern: str | None = None
    choices: tuple[str, ...] = ()
    minimum: int = 0
    width: int = 0
    samples: tuple[str, ...] = ()
    template: str | None = None


@dataclass(frozen=True)
class ResourceSpec:
    name: str
    template: str | None
    location: str | None = None
    reader_field: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExampleSpec:
    resource: str
    input: str
    expected: dict[str, str | int] = field(default_factory=dict)
    error_code: str | None = None
    source: str = "name"


@dataclass(frozen=True)
class Definition:
    spec_version: int
    fields: dict[str, FieldSpec]
    resources: dict[str, ResourceSpec]
    readers: dict[str, str]
    examples: tuple[ExampleSpec, ...]
    roots: dict[str, str] = field(default_factory=dict)
    normalize: dict[str, str] = field(default_factory=dict)
    # Where declarations sit in the rule text, keyed like ("example", 0, "input"). Editors
    # and test reports use it; it is not part of the model, so the export leaves it out.
    spans: dict[tuple[str | int, ...], tuple[int, int]] = field(
        default_factory=dict, compare=False, repr=False
    )

    def to_dict(self) -> dict[str, Any]:
        """Export the model with JSON-native containers; text regexes keep Python re semantics."""
        model = asdict(self)
        del model["spans"]
        return _jsonable(model)


@dataclass(frozen=True)
class ExampleResult:
    """One inline example or rejection after a run. Spans point into the rule text."""

    example: ExampleSpec
    span: tuple[int, int] | None = None
    failures: tuple[Diagnostic, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.failures


def validate_field_spec(spec: FieldSpec, sample_spans: Sequence[tuple[int, int]] = ()) -> None:
    """Field-level rules, applied by the parser once a rule has been read."""
    if spec.name in RESERVED_FIELDS:
        fail("reserved_field", f"The field {spec.name!r} is reserved for resource templates.")
    if spec.kind == "text":
        try:
            regex = re.compile(spec.pattern or "")
        except re.error as exc:
            fail("invalid_pattern", f"{spec.name}: {exc}")
        if regex.fullmatch(""):
            fail("empty_field", f"{spec.name} must not accept an empty string.")
        for index, value in enumerate(spec.samples):
            if not regex.fullmatch(value):
                fail(
                    "invalid_sample",
                    f"Sample {value!r} for {spec.name!r} does not match {spec.pattern!r}.",
                    field=spec.name,
                    expected=spec.pattern,
                    actual=value,
                    span=sample_spans[index] if sample_spans else None,
                )
    elif spec.kind == "integer":
        if spec.minimum < 0 or spec.width < 0:
            fail("invalid_integer", "Minimum and padding must be nonnegative.")
    elif spec.kind == "enum":
        if not spec.choices or any(not value for value in spec.choices):
            fail("empty_field", f"{spec.name} has an empty enum choice.")
        if len(set(spec.choices)) != len(spec.choices):
            fail("duplicate_choice", f"{spec.name} has duplicate choices.")


def check_root(name: str, path: str) -> None:
    """Roots are literal prefixes: no slots, no trailing slash, forward slashes only."""
    if not path:
        fail("invalid_root", f"Root {name!r} must not be empty.", field=name)
    if "{" in path or "}" in path:
        fail("invalid_root", f"Root {name!r} must not contain braces.", field=name, actual=path)
    if "\\" in path:
        fail("invalid_root", f"Root {name!r} must use forward slashes.", field=name, actual=path)
    if path.endswith("/"):
        fail("invalid_root", f"Root {name!r} must not end with a slash.", field=name, actual=path)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


@dataclass(frozen=True)
class Validation:
    resource: str
    input: str
    fields: dict[str, str | int]
    diagnostics: tuple[Diagnostic, ...] = ()
    source: str = "name"

    @property
    def valid(self) -> bool:
        return not self.diagnostics

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, **asdict(self)}


@dataclass(frozen=True)
class Inspection:
    status: str
    matches: tuple[Validation, ...]
    candidates: tuple[Validation, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "matches": [item.to_dict() for item in self.matches],
            "candidates": [item.to_dict() for item in self.candidates],
        }
