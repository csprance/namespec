# Names and their expected meaning

[assets.csv](assets.csv) is the introductory editable test table. The [Studio example](../../examples/studio.md) adds tables for jobs, entities, files, and cameras. Each row is an independent expected answer written by a human. Pytest discovers every CSV in this folder and runs every row. Expectations are never generated from the parser being tested.

Open the CSV in a table-capable editor or import it into a spreadsheet as UTF-8. Keep input names and paths as text so their spelling and padding stay intact. The repository file is the source of truth; save edits back as CSV.

## Reading a row

| Column | Meaning |
| --- | --- |
| `case` | A unique readable ID, shown in pytest output. |
| `schema` | Optional column selecting `examples/<schema>.names`. Blank or omitted uses the CSV filename stem. |
| `input` | The exact name or path to inspect. |
| `source` | `name` for a basename; `location` for a full path. |
| `resource` | The resource type this row validates against and whose metadata is listed. |
| `matches` | Optional column listing every expected match for a valid input, separated by semicolons. Blank means only `resource` matches. Multiple matches assert ambiguity and require an explicit resource when parsing. Leave blank for invalid rows. |
| `valid` | Exactly `true` or `false`. |
| `field.asset_name`, `field.lod`, etc. | The complete expected parsed metadata, one field per column. |
| `field.version:int` | An expected integer. Thus `v004` in the input produces `4` here. |
| `context.job` | Extra context supplied for location resolution. This is distinct from metadata actually present in the input. |
| `reader` | Expected registered-reader ID, if this row checks reader selection. It does not open the file. |
| `location` | The exact expected location, if this row checks resolution. No filesystem access occurs. |
| `diagnostics` | Expected errors, such as `invalid_field:lod`. Separate multiple errors with semicolons. Use `pattern_mismatch` when no field can be assigned. |
| `notes` | A plain-language explanation of what the row demonstrates. |

**A blank metadata cell means the field must be absent, not “skip this check.”** Invalid inputs still list every recoverable field. Conflicting or invalid fields stay blank. All error code/field pairs must match exactly, including repeated errors; their order does not matter.

For example, `Donut_ultra_v004.abc` is invalid, but its row still expects `asset_name=Donut`, `version=4`, and `filetype=abc`. Its LOD cell is blank and its error is `invalid_field:lod`.

`<LF>`, `<CR>`, and `<TAB>` in an input represent actual newline, carriage-return, and tab characters. These visible markers keep special-character cases on one physical CSV line. Everything else is literal, including backslashes.

## Adding cases

1. Copy a similar row and give it a new `case` ID.
2. Enter the input and its expected meaning. Do not copy the engine's output without reviewing it.
3. Run `uv run pytest tests/test_name_cases.py -v` from the repository root.

Run one row with `uv run pytest tests/test_name_cases.py -k short_version -v`.

To test another convention, create `examples/<name>.names` and `tests/cases/<name>.csv`. To split a convention across smaller tables, supply its name in the optional `schema` column, as the Studio tables do. Keep the required control columns above and add any `field.<name>` or `context.<name>` columns needed; append `:int` for integers. No Python test edits are needed. Rows with malformed headers, duplicate IDs, missing schemas, or inconsistent expectations fail collection with a file and line reference.

The naming table covers concrete names and paths. Python tests still cover API behavior such as callbacks, wrong Python value types, ambiguous catalogs, invalid rule definitions, and the inline example feature. Generated round-trip tests supplement these independent expected answers.
