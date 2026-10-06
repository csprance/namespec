# Namespec

Readable rules for names, metadata, and resource locations. This is an experimental Python-first package; its public-release license is still undecided.

Python 3.10+ runs the engine. [textX](https://textx.github.io/textX/) parses the rule language. Rule documents contain data and named capabilities; they do not execute Python. The custom layer defines naming semantics, structured diagnostics, generation, and resource operations, which the evaluated template libraries did not provide together.

## Try it

```powershell
uv sync
uv run namespec examples/assets.names inspect Donut_high_v004.abc
uv run namespec examples/assets.names inspect Donut_ultra_v004.abc --resource asset_model
uv run namespec examples/assets.names test
uv run namespec examples/assets.names export
```

The CLI writes JSON. Exit codes: `0` success, `1` invalid/ambiguous input or failed examples, `2` definition/operation error.

## Define rules

```text
spec 1

job        = text matching "[A-Za-z0-9-]+" examples "commercial42"
asset_name = text matching "[A-Za-z][A-Za-z0-9]*" examples "Donut", "Chair"
lod        = one of "low", "mid", "high"
version    = integer minimum 1 padded to 3 digits
filetype   = one of "abc", "usd"

readers {
    abc = "alembic"
    usd = "usd"
}

resource asset_model {
    name = "{asset_name}_{lod}_v{version}.{filetype}"
    location = "/jobs/{job}/assets/{asset_name}/model/{lod}/{name}"
    reader = readers[filetype]
}

example asset_model {
    input = "Donut_high_v004.abc"
    expect {
        asset_name = "Donut"
        lod = "high"
        version = 4
        filetype = "abc"
    }
}

reject asset_model {
    input = "Donut_high_v4.abc"
    expect = "noncanonical_field"
}
```

Read from simple to complex: field rules, reader mappings, resource templates, then executable examples. The language also allows definitions to follow their uses. `//` starts a comment. The complete example in [examples/assets.names](examples/assets.names) includes additional negative cases.

## Python API

```python
from namespec import Catalog

catalog = Catalog.from_file("examples/assets.names")
resource = catalog.parse("Donut_high_v004.abc")
assert resource.kind == "asset_model"
assert resource.fields["version"] == 4
assert resource.name == "Donut_high_v004.abc"

location = resource.locate(job="commercial42")
assert location == "/jobs/commercial42/assets/Donut/model/high/Donut_high_v004.abc"

# A full location supplies job context and checks repeated fields for equality.
same = catalog.parse(location, source="location")
assert same.fields["job"] == "commercial42"

result = catalog.validate("Donut_ultra_v004.abc", "asset_model")
assert not result.valid
assert result.diagnostics[0].field == "lod"
assert result.fields["version"] == 4

assert not catalog.check_examples()
for name in catalog.samples("asset_model", limit=10):
    assert catalog.parse(name).name == name
```

`Catalog.from_string(source)` is also available. `format(resource, **fields)` generates names, and `locate(resource, **fields)` generates locations from metadata. `inspect(text)` returns all exact matches and structurally aligned invalid candidates; it never silently chooses the first match. `parse(text, resource="asset_model")` selects a convention explicitly. Errors raise `NameSpecError` with a `diagnostics` list.

Fields returned by a failed validation are partial, provisional metadata. Invalid or conflicting fields are omitted. Only successful parsing produces a `Resource`.

## Readers

A reader ID names a capability supplied by the host application:

```python
# Your application supplies read_alembic(path). The package does not ship DCC readers.
catalog.register_reader("alembic", read_alembic)
data = resource.read(job="commercial42")
```

Parsing and locating do no filesystem I/O. `read()` explicitly calls the registered handler with a `pathlib.Path`; that handler opens and validates content and owns file errors. A missing handler produces `unavailable_reader`. Context cannot overwrite parsed metadata. Location derivation does not prove existence, and basename parsing cannot infer missing project context.

## Version 1 semantics and limits

- Names and locations must match the whole input, including case. Input is never silently normalized.
- `name` is a reserved filename-template reference usable in a location. All other slots refer to declared fields. A location must include all filename fields.
- Repeated slots must have identical spellings. Conflicts produce `conflicting_field` diagnostics with input offsets.
- Fields must be separated by punctuation. Literal delimiter punctuation is reserved and cannot occur inside field values. For the supplied convention this excludes underscores, dots, slashes, and backslashes from asset names. This deliberate first-version restriction makes token boundaries reliable. Whitespace present in template literals is also reserved.
- Integers are nonnegative, with an explicit minimum. Padding is minimum width: `004` and `1000` are canonical for width 3; `4`, `0004`, and non-ASCII digits are not. Generation requires Python integers, not strings or booleans.
- Empty aligned fields yield `missing_field`. Wrong field values yield `invalid_field`. When separators or an entire slot are missing, the result may be `pattern_mismatch`, without a guessed partial parse.
- `example` asserts the complete typed field dictionary. `reject` asserts that a particular diagnostic code occurs. These examples validate basenames; location assertions currently belong in Python tests.
- Sample generation combines authored text examples, enum choices, and integer minima. It does not invert arbitrary regexes or prove business-rule correctness.
- `definition.to_dict()` exports the draft JSON-compatible model. There is no JSON import or second-language runtime yet. Text patterns currently have Python `re` semantics, so export alone is not a cross-language compatibility guarantee.
- Imports, aliases, optional groups, automatic schema migrations, filesystem searching, fuzzy recovery, and bundled asset readers are not implemented yet. Add these against concrete conventions rather than broadening the language speculatively.

## Development

For `.names` editing in VS Code, install the [local Namespec language extension](editors/vscode/README.md). It highlights templates and field references, supports Ctrl+click/F12 navigation to declarations, toggles `//` comments, and adds bracket/quote completion.

The human-editable [name test table](tests/cases/assets.csv) lists inputs, expected resource types, validity, metadata fields, readers, locations, and errors. Adding a row adds a pytest case automatically. See [the table guide](tests/cases/README.md) for column meanings and adding another convention.

```powershell
uv run pytest
uv run pytest tests/test_name_cases.py -v
uv run ruff check .
uv run ruff format --check .
uv build
```

Nothing has been published to PyPI.

## Studio conventions

The [studio example](examples/studio.md) uses fictional projects and assets to demonstrate [readable rules](examples/studio.names) and four CSV tables covering jobs, entities, files, and cameras. It includes relative render/publish locations and explicit expectations for names with multiple interpretations. The accompanying notes explain the example conventions and their limits.
