# namespec

Python 3.10+ naming-rule language and library for typed fields, filenames and resource locations, plus a VS Code extension for `.names` files. The base Python library has no runtime dependencies; filesystem spelling validation is optional.

## Start here

- `README.md` introduces the workflow; `docs/guide.md` and `docs/reference.md` define language/API contracts. `developer.md` owns maintenance and validation procedures.
- `src/namespec/parser.py` reads declarations; `template.py` handles template parsing/formatting; `models.py` and `catalog.py` implement definitions and resources.
- `src/namespec/policies.py` contains optional filesystem policies; `cli.py` implements the `namespec` command and editor-facing operations.
- `examples/guide.names`, `advanced.names` and `studio.names` are executable language examples.
- `tests/` combines focused tests, Hypothesis properties and independent CSV expectations under `tests/cases/`.
- `editors/vscode/` owns the extension, grammar, Node tests and packaging; read its `README.md` before editor work.
- `.github/workflows/ci.yml` defines Python 3.10-3.14 checks and editor checks on Windows, Linux and macOS.

## Local checks

```sh
uv sync --locked --all-extras
uv run --locked --all-extras pytest -q
uv run --locked --all-extras ruff check .
uv run --locked --all-extras ruff format --check .
uv run --locked namespec examples/guide.names test
uv build
```

Also exercise the base installation with `uv run --locked --no-extra filesystem pytest -q` when changing optional-dependency boundaries. For editor changes, run `npm ci` then `npm test` from `editors/vscode` after syncing Python; Node is a development dependency, not a Python runtime dependency. The extension-host acceptance command is documented separately in `editors/vscode/README.md`.

## Contracts to preserve

- Parsing returns a resource only for one valid interpretation. Preserve diagnostics, source selection, typed fields, padding and round-trip behavior across `name` and `location` templates.
- Definitions are immutable snapshots. Compile a new catalog to change rules; `load_rules.cache_clear()` deliberately invalidates the loader cache.
- Keep resource subclasses/readers explicitly registered. Do not turn rule parsing into dynamic code execution or implicit plugin discovery.
- Deriving a path or next version does not access, reserve or write the represented file. Discovery/storage and publish policy belong to the caller.
- Keep the optional filesystem validator optional, including missing-dependency behavior. Use existing libraries for standard validation instead of duplicating them.
- Update guide/reference, executable examples and independent expectations together for language changes; avoid tests that only restate the implementation.
- The editor must preserve workspace-trust restrictions, cancellation/request ordering and accurate diagnostics/test identity.
- Packaging checks must test the installed wheel, not only editable imports. Build release archives from a clean checkout/archive and inspect contents, since local Git excludes do not control Hatch's sdist selection.
