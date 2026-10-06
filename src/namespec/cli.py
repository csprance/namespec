"""Small JSON-emitting command line interface."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from .catalog import Catalog
from .models import NameSpecError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate names against readable rules.")
    parser.add_argument("schema", help="Path to a .names rule document")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Identify and validate a name or location")
    inspect.add_argument("text")
    inspect.add_argument("--resource")
    inspect.add_argument("--source", choices=["name", "location"], default="name")
    commands.add_parser("test", help="Run the rule document's expected-result examples")
    commands.add_parser("export", help="Export the draft compiled model as JSON")
    for operation in ("format", "locate"):
        command = commands.add_parser(operation)
        command.add_argument("resource")
        command.add_argument("fields", help='JSON object, e.g. {"version": 4}')
    args = parser.parse_args(argv)
    try:
        catalog = Catalog.from_file(args.schema)
        if args.command == "inspect":
            result = (
                catalog.validate(args.text, args.resource, source=args.source)
                if args.resource
                else catalog.inspect(args.text, source=args.source)
            )
            output = result.to_dict()
            success = result.valid if args.resource else result.status == "valid"
        elif args.command == "test":
            failures = catalog.check_examples()
            output = {
                "passed": not failures,
                "examples": len(catalog.definition.examples),
                "failures": [asdict(item) for item in failures],
            }
            success = not failures
        elif args.command == "export":
            output = catalog.definition.to_dict()
            success = True
        else:
            fields = json.loads(args.fields)
            if not isinstance(fields, dict):
                parser.error("fields must be a JSON object")
            output = {args.command: getattr(catalog, args.command)(args.resource, **fields)}
            success = True
        print(json.dumps(output, indent=2))
        return 0 if success else 1
    except NameSpecError as exc:
        print(json.dumps({"diagnostics": [asdict(item) for item in exc.diagnostics]}, indent=2))
        return 2
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
