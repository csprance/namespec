# Namespec

A file browser needs to know which asset and version a filename describes. A save dialog needs to explain why a proposed name is invalid. A publisher needs to build the right output path. **Namespec lets all three use the same naming rules.**

Use it when filenames and folder layouts carry information your tools depend on. It turns that information into typed fields and uses those fields to build valid names and paths. For simply opening a file, use `pathlib.Path` directly.

## The everyday workflow

A **catalog** is your loaded set of naming rules. You load it once, give it a filename or path, and get a **resource** back: the recognized kind, its field values, and methods for working with them.

After the setup below, save this as `try_namespec.py` in the repository root and run `uv run --locked python try_namespec.py`:

```python
from namespec import Catalog

catalog = Catalog.from_file("examples/guide.names")
model = catalog.parse("Donut_high_v004.abc")

# A browser can sort by a number instead of extracting digits itself.
print(model["version"])  # 4

# A save tool can propose the next name with the right padding.
print(model.replace(version=model["version"] + 1).name)  # Donut_high_v005.abc

# The filename contains no project or mount. Find out what is missing.
print(model.missing_context)  # ('root', 'job')
located = model.with_context(root="windows", job="show17")
print(located.path.as_posix())
# J:/jobs/show17/assets/Donut/high/Donut_high_v004.abc
```

The next version here is a proposal. Your save tool still decides whether that version is available and writes the file. Parsing and deriving paths do not access the described files.

| What your tool needs | Use | Why |
| --- | --- | --- |
| Work with a filename or path | `catalog.parse(value)` | Return a resource only when the input has one valid interpretation |
| Explain a bad value in a form | `catalog.validate(value, "model")` | Get diagnostics the UI can display |
| Investigate an unknown input | `catalog.inspect(value)` | See matching kinds and candidate errors |
| Change a version or shot | `resource.replace(...)` | Keep formatting and dependent composite fields consistent |
| Supply a project or mount | `resource.with_context(...)` | Turn a filename into a resource at its declared location |
| Derive a render or task folder | `resource.related("render", ...)` | Reuse the current resource's fields with another rule |
| Use normal filesystem operations | `resource.path` | Get a native `Path` with `.parent`, `.exists()`, `.open()`, etc. |

## How do I know which names and options exist?

The catalog describes its own vocabulary:

- `catalog.resources.keys()`: kinds you can parse, such as `"model"` or `"scene"`.
- `catalog.roots`: mount labels and prefixes, such as `"windows": "J:/jobs"`.
- `resource.keys()`: fields this input supplied, such as `"asset"` and `"version"`.
- `resource.missing_context`: values still needed to construct its location.
- `catalog.fields["version"]`: that field's rule, including its bounds and padding.
- `help(catalog.parse)`: the method's arguments, allowed source options, and purpose.

`"model"`, `"version"`, and `"windows"` come from the chosen rule file. A different catalog can use different names.

**You normally do not choose a source.** The default `source="auto"` tries the rule's `name` and `location` templates. Choose `"name"` only when a caller requires a filename, such as a filename-only save box. Choose `"location"` when a caller must check the complete folder layout, such as a publish check. These are built-in choices, explained with an example in [when to select a source](docs/reference.md#when-to-select-a-source).

## Set up the example

Namespec requires Python 3.10 or newer. Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run:

```console
git clone https://github.com/csprance/namespec.git
cd namespec
uv sync --locked
uv run --locked namespec examples/guide.names test
```

If you already have the checkout, start with `uv sync --locked` from the folder containing `pyproject.toml`. The test command should print `9 passed`. The [guide](docs/guide.md#1-get-a-working-setup) explains setup in more detail.

## When do I write rules?

Write or change a `.names` file when you own the naming convention. If your team already supplies one, load that catalog and use its resources.

For example, this rule says that a model filename carries four values, and versions must use at least three digits:

```text
spec 1

asset   = text matching "[A-Z][a-z]+" examples "Donut"
lod     = one of "low", "mid", "high"
version = integer minimum 1 padded to 3 digits
ext     = one of "abc", "usd"

resource model {
    name = "{asset}_{lod}_v{version}.{ext}"
}
```

That is why `Donut_high_v004.abc` returns integer version `4`, and `Donut_high_v4.abc` is rejected with a padding error. Executable examples beside the rules protect the convention when it changes.

## Read next

| Need | Read |
| --- | --- |
| Understand the workflow, then author your own convention | [Guide](docs/guide.md) |
| Look up an argument, construct, or error | [Reference](docs/reference.md) |
| Explore a complete small convention | [Annotated beginner rules](examples/guide.names) |
| Use signed frames, bounds, and regex features | [Advanced rules](examples/advanced.names) |
| Study a larger convention | [Studio example](examples/studio.names) and [CSV tests](tests/cases/README.md) |
| Get live feedback while editing rules | [VS Code setup](editors/vscode/README.md) |
| Contribute or package the library | [Developer guide](developer.md) |
| Update an existing integration | [Changelog](CHANGELOG.md) |

Namespec is MIT licensed and currently alpha. The base library has no runtime dependencies. Optional [filesystem policies](docs/guide.md#14-opt-into-filesystem-spelling-checks) check platform filename spelling; file discovery, version reservation, and storage operations remain the host tool's responsibility.
