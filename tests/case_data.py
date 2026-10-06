"""Read human-authored CSV expectations without deriving answers from the naming engine."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parents[1]
CASE_DIRECTORY = Path(__file__).parent / "cases"
CONTROL_COLUMNS = {
    "case",
    "input",
    "source",
    "resource",
    "valid",
    "reader",
    "location",
    "diagnostics",
    "notes",
}
OPTIONAL_COLUMNS = {"schema", "matches"}


@dataclass(frozen=True)
class NameCase:
    id: str
    schema: Path
    input: str
    source: str
    resource: str
    valid: bool
    fields: dict[str, str | int]
    context: dict[str, str | int]
    reader: str
    location: str
    diagnostics: tuple[tuple[str, str | None], ...]
    notes: str
    matches: tuple[str, ...]


def _metadata(row: dict[str, str], prefix: str) -> dict[str, str | int]:
    values: dict[str, str | int] = {}
    for column, value in row.items():
        if not column.startswith(prefix) or value == "":
            continue
        name, _, kind = column.removeprefix(prefix).partition(":")
        values[name] = int(value) if kind == "int" else value
    return values


def load_cases(path: Path) -> list[NameCase]:
    """Use the table stem as its schema, unless a row supplies a schema column."""
    cases = []
    seen = set()
    # utf-8-sig accepts ordinary UTF-8 and Excel's optional UTF-8 byte order mark.
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames or []
        if len(set(headers)) != len(headers) or not CONTROL_COLUMNS.issubset(headers):
            raise ValueError(f"{path}: missing or duplicate column headers")
        metadata_names: set[tuple[str, str]] = set()
        for column in headers:
            if column in CONTROL_COLUMNS | OPTIONAL_COLUMNS:
                continue
            prefix, separator, field = column.partition(".")
            name, _, kind = field.partition(":")
            key = (prefix, name)
            if (
                separator != "."
                or prefix not in {"field", "context"}
                or not name.isidentifier()
                or kind not in {"", "int"}
                or key in metadata_names
            ):
                raise ValueError(f"{path}: invalid or duplicate metadata column {column!r}")
            metadata_names.add(key)
        for row in reader:
            label = f"{path}:{reader.line_num} ({row.get('case', '')})"
            try:
                if None in row or None in row.values():
                    raise ValueError("row has the wrong number of cells")
                if not row["case"] or row["case"] in seen:
                    raise ValueError("case IDs must be nonempty and unique")
                if row["source"] not in {"name", "location"}:
                    raise ValueError("source must be name or location")
                if not row["resource"] or row["valid"] not in {"true", "false"}:
                    raise ValueError("supply a resource and true/false validity")
                schema_name = row.get("schema") or path.stem
                if not schema_name.isidentifier():
                    raise ValueError("schema must be a simple name without a path or extension")
                schema = ROOT / "examples" / f"{schema_name}.names"
                if not schema.is_file():
                    raise ValueError(f"missing matching schema {schema}")
                diagnostics = []
                for item in filter(None, row["diagnostics"].split(";")):
                    code, separator, field = item.partition(":")
                    if not code.isidentifier() or (separator and not field.isidentifier()):
                        raise ValueError(f"invalid diagnostic {item!r}")
                    diagnostics.append((code, field or None))
                valid = row["valid"] == "true"
                matches = tuple((row.get("matches") or row["resource"]).split(";"))
                if (
                    len(set(matches)) != len(matches)
                    or any(not name.isidentifier() for name in matches)
                    or row["resource"] not in matches
                ):
                    raise ValueError("matches must list unique resource names including resource")
                if not valid and row.get("matches"):
                    raise ValueError("matches is only supported for valid rows")
                if valid == bool(diagnostics):
                    raise ValueError(
                        "valid rows need no diagnostics; invalid rows need diagnostics"
                    )
                if not valid and (row["reader"] or row["location"]):
                    raise ValueError("invalid rows cannot assert successful resource operations")
                fields = _metadata(row, "field.")
                context = _metadata(row, "context.")
            except ValueError as exc:
                raise ValueError(f"{label}: {exc}") from exc
            text = row["input"]
            for marker, character in (("<LF>", "\n"), ("<CR>", "\r"), ("<TAB>", "\t")):
                text = text.replace(marker, character)
            cases.append(
                NameCase(
                    f"{path.stem}/{row['case']}",
                    schema,
                    text,
                    row["source"],
                    row["resource"],
                    valid,
                    fields,
                    context,
                    row["reader"],
                    row["location"],
                    tuple(diagnostics),
                    row["notes"],
                    matches if valid else (),
                )
            )
            seen.add(row["case"])
    if not cases:
        raise ValueError(f"{path}: add at least one case")
    return cases


def all_cases() -> list[NameCase]:
    paths = sorted(CASE_DIRECTORY.glob("*.csv"))
    if not paths:
        raise ValueError(f"No CSV cases found in {CASE_DIRECTORY}")
    return [case for path in paths for case in load_cases(path)]
