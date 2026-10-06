"""Plain data shared by the compiler, runtime, and JSON output."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    field: str | None = None
    expected: Any = None
    actual: Any = None
    span: tuple[int, int] | None = None


class NameSpecError(ValueError):
    """A definition or operation failed, with machine-readable diagnostics."""

    def __init__(self, diagnostics: list[Diagnostic]):
        self.diagnostics = diagnostics
        super().__init__("; ".join(item.message for item in diagnostics))


def fail(code: str, message: str, **details: Any) -> None:
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


@dataclass(frozen=True)
class ResourceSpec:
    name: str
    template: str
    location: str | None = None
    reader_field: str | None = None


@dataclass(frozen=True)
class ExampleSpec:
    resource: str
    input: str
    expected: dict[str, str | int] = field(default_factory=dict)
    error_code: str | None = None


@dataclass(frozen=True)
class Definition:
    spec_version: int
    fields: dict[str, FieldSpec]
    resources: dict[str, ResourceSpec]
    readers: dict[str, str]
    examples: tuple[ExampleSpec, ...]

    def to_dict(self) -> dict[str, Any]:
        """Export the draft model; text regexes currently use Python re semantics."""
        return asdict(self)


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
