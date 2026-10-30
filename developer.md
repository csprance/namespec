# Development

This page covers working on the package and editor extension. For using Namespec, start with the [guide](docs/guide.md); consult the [reference](docs/reference.md) for language and API contracts.

Use Python 3.10 or newer and uv. Node.js is needed for editor tests; it is not a Namespec runtime dependency.

```sh
uv sync --locked --all-extras
uv run --locked --all-extras pytest -q
uv run --locked --all-extras ruff check .
uv run --locked --all-extras ruff format --check .
uv build
```

`--all-extras` installs the optional filesystem validator. The base library has no runtime dependencies. Hypothesis is a development dependency; its generated cases complement the independently authored CSV expectations. Use `uv run --locked --no-extra filesystem pytest -q` to exercise the base installation; filesystem integration tests skip when that extra is unavailable, while missing-dependency handling is still tested.

Run editor checks from `editors/vscode` after syncing the Python environment:

```sh
npm ci
npm test
```

The editor suite includes the real Python CLI and a mocked VS Code controller for request ordering, cancellation, exclusions and test identity. The isolated VS Code extension-host test in `editors/vscode/test/extension-host.cjs` additionally checks actual activation, navigation and live diagnostics; see the [editor README](editors/vscode/README.md#maintaining-the-extension) for invocation details.

CI runs the Python suite on Python 3.10 through 3.14 on Windows, Linux and macOS. It builds a source distribution and wheel, replaces the editable project with that wheel while keeping the locked test dependencies, verifies imports come from site-packages, and runs the suite again. Editor tests run on all three platforms. A successful local run does not imply the hosted CI matrix has run.

Definition mappings are immutable snapshots. Compile a new catalog to change rules; `load_rules.cache_clear()` invalidates the process-wide loader cache. Resource subclasses and readers remain explicitly registered runtime behavior.

Build release distributions from a clean checkout or Git archive of the release commit. Hatch's source-distribution file selection does not honor machine-specific `.git/info/exclude` entries, so building from a working checkout can include local fixtures. Inspect archive contents before uploading release assets.
