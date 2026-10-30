"""Small command line interface. Output is JSON, except the ``test`` report, which is written
for people unless ``--json`` asks for the same results as data."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .catalog import Catalog
from .models import Diagnostic, ExampleResult, NameSpecError, position


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate names against readable rules.")
    parser.add_argument("schema", help="Path to a .names rule document, or - to read stdin")
    parser.add_argument(
        "--strict", action="store_true", help="Reject generated names that change field values"
    )
    parser.add_argument(
        "--filesystem", choices=["posix", "windows", "portable"], help="Check filesystem components"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Identify and validate a name or location")
    inspect.add_argument("text")
    inspect.add_argument("--resource")
    inspect.add_argument("--source", choices=["auto", "name", "location"], default="auto")
    test = commands.add_parser("test", help="Run the rule document's examples and rejections")
    test.add_argument("--json", action="store_true", help="Report every example as JSON")
    export = commands.add_parser("export", help="Export the compiled model as JSON")
    export.add_argument("--output", "-o", help="Write the JSON model to this file instead")
    for operation in ("format", "locate"):
        command = commands.add_parser(operation)
        command.add_argument("resource")
        command.add_argument("fields", help='JSON object, e.g. {"version": 4}')
    args = parser.parse_args(argv)
    label = "<stdin>" if args.schema == "-" else args.schema
    readable = args.command == "test" and not args.json
    try:
        # Read stdin as bytes so offsets match the editor buffer, CRLF included.
        if args.schema == "-":
            source = sys.stdin.buffer.read().decode("utf-8")
        else:
            source = Path(args.schema).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print(f"{label}: {exc}" if readable else json.dumps({"error": str(exc)}))
        return 2
    try:
        catalog = Catalog.from_string(source, strict=args.strict, filesystem=args.filesystem)
    except NameSpecError as exc:
        if readable:
            for item in exc.diagnostics:
                print(f"{place(label, source, item.span)}{item.message}")
        else:
            report = [located(source, item) for item in exc.diagnostics]
            print(json.dumps({"diagnostics": report}, indent=2))
        return 2
    if args.command == "test":
        results = catalog.run_examples()
        if readable:
            print_results(label, source, results)
        else:
            output = {
                "passed": all(result.passed for result in results),
                "examples": [example_report(source, result) for result in results],
            }
            print(json.dumps(output, indent=2))
        return 0 if all(result.passed for result in results) else 1
    try:
        if args.command == "inspect":
            result = (
                catalog.validate(args.text, args.resource, source=args.source)
                if args.resource
                else catalog.inspect(args.text, source=args.source)
            )
            output = result.to_dict()
            success = result.valid if args.resource else result.status == "valid"
        elif args.command == "export":
            output = catalog.definition.to_dict()
            if args.output:
                Path(args.output).write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
                output = {"written": args.output, "resources": sorted(output["resources"])}
            success = True
        else:
            fields = json.loads(args.fields)
            if not isinstance(fields, dict):
                parser.error("fields must be a JSON object")
            value = getattr(catalog, args.command)(args.resource, **fields)
            output = {args.command: value.as_posix() if isinstance(value, Path) else value}
            success = True
        print(json.dumps(output, indent=2))
        return 0 if success else 1
    except NameSpecError as exc:
        print(json.dumps({"diagnostics": [asdict(item) for item in exc.diagnostics]}, indent=2))
        return 2
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2


def print_results(label: str, source: str, results: list[ExampleResult]) -> None:
    """One ``file:line:column:`` line per failure, which terminals and editors link."""
    for result in results:
        example = result.example
        kind = "reject" if example.error_code else "example"
        for failure in result.failures:
            where = place(label, source, failure.span or result.span)
            print(f"{where}{kind} {example.resource}: {failure.message}")
    failed = sum(not result.passed for result in results)
    if not results:
        print("No examples to run.")
    else:
        print(f"{len(results) - failed} passed" + (f", {failed} failed" if failed else ""))


def place(label: str, source: str, span: tuple[int, int] | None) -> str:
    if span is None:
        return f"{label}: "
    line, column = position(source, span[0])
    return f"{label}:{line}:{column}: "


def located(source: str, item: Diagnostic) -> dict[str, Any]:
    """A diagnostic about the rule text, with the line and column of its span."""
    report = asdict(item)
    if item.span is not None:
        report["line"], report["column"] = position(source, item.span[0])
    return report


def example_report(source: str, result: ExampleResult) -> dict[str, Any]:
    example = result.example
    report: dict[str, Any] = {
        "resource": example.resource,
        "kind": "reject" if example.error_code else "example",
        "source": example.source,
        "input": example.input,
        "passed": result.passed,
        "span": result.span,
    }
    if result.span is not None:
        report["line"], report["column"] = position(source, result.span[0])
    report["failures"] = [located(source, item) for item in result.failures]
    return report


if __name__ == "__main__":
    raise SystemExit(main())
