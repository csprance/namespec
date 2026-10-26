"""Plain data shared by the parser, runtime, and JSON output."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
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
    """A definition or operation failed, with machine-readable diagnostics."""

    def __init__(self, diagnostics: list[Diagnostic]):
        self.diagnostics = diagnostics
        super().__init__("; ".join(item.message for item in diagnostics))


def fail(code: str, message: str, **details: Any) -> NoReturn:
    raise NameSpecError([Diagnostic(code, message, **details)])


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

    def to_dict(self) -> dict[str, Any]:
        """Export the model with JSON-native containers; text regexes keep Python re semantics."""
        return _jsonable(asdict(self))


def validate_field_spec(spec: FieldSpec) -> None:
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
        if any(not regex.fullmatch(value) for value in spec.samples):
            fail("invalid_sample", f"An example violates field {spec.name!r}.")
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
