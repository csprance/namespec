# Fictional studio naming example

[studio.names](studio.names) demonstrates a small production naming system using fictional projects, assets, identifiers, and sample values. MoonOrchard is an imaginary show, KestrelQuest an imaginary adventure series, and PixelTea2042 an imaginary campaign. These examples are teaching data, not a production studio's naming policy.

The templates come first, followed by reusable field rules. Optional tags, job suffixes, and frame components use separate resource definitions because Namespec does not yet support optional template groups.

## Editable examples

Each CSV contains sample names, expected types, extracted metadata in separate columns, and explanations. Valid examples sit alongside malformed and ambiguous inputs so changes can be checked against explicit expectations.

| Table | Contents |
| --- | --- |
| [Jobs](../tests/cases/studio_jobs.csv) | Short and descriptive job folders, optional suffixes, missing values. |
| [Entities](../tests/cases/studio_entities.csv) | Episodes, sequences, shots, assets, padding, overlapping interpretations. |
| [Files](../tests/cases/studio_files.csv) | Workfiles and tags, renders, publishes, relative paths, repeated-version conflicts. |
| [Cameras](../tests/cases/studio_cameras.csv) | Shot and asset cameras, descriptor casing, variants, forbidden version suffixes. |

All four tables select `schema=studio`. The [table guide](../tests/cases/README.md) explains the columns. Expected answers are authored independently of the naming engine.

```python
from namespec import Catalog

catalog = Catalog.from_file("examples/studio.names")
item = catalog.parse("prop_Lantern_mdl_model_v017.abc", "asset_publish")
assert item.fields == {
    "asset_type": "prop",
    "asset_name": "Lantern",
    "task": "mdl",
    "publish_type": "model",
    "version": "017",
    "ext": "abc",
}
assert item.locate() == ("pub/mdl/outputs/prop_Lantern_mdl_v017/prop_Lantern_mdl_model_v017.abc")
```

## Context is part of identification

A basename can match more than one convention. `prop_Lantern_mdl_model_v017.abc` fits both an asset render and a published output. The relative `work/.../renders/...` or `pub/.../outputs/...` path distinguishes them. Likewise, `731_037` could be a sequence or a job folder; `NVA_086` could be a sequence or an asset while asset-type codes remain unrestricted.

`inspect()` returns every match. `parse()` requires a resource hint when multiple matches remain. The CSV `matches` column lists all expected interpretations, so a change that hides or introduces a match fails the tests. `resource` identifies the interpretation whose metadata the row checks.

## Example conventions and limits

- Jobs accept a short form such as `68219_MoonOrchard`, a description such as `68219_MoonOrchard_LaunchFilm`, and up to two extra labels such as `45sec_Festival`. Each form has its own resource definition.
- Assets have a short identity such as `bldg_SkyDepot`. Adding a task and version produces `bldg_SkyDepot_mdl_v009`; workfiles add an extension and may include a tag. The shot examples use `NVA_086_0070` and `731_037_0260`.
- Asset types and tasks accept letters only. Most other labels accept ASCII letters and digits. Example values illustrate the syntax rather than define a fixed vocabulary. Extensions are metadata; they do not install or invoke any DCC tooling.
- Episode, sequence, shot, job number, and version stay text to preserve leading zeroes. Sequences require three digits, shots four, and versions exactly three. The version syntax accepts `000` and rejects `1000`. This differs from the minimum-width integer example in `assets.names`.
- A frame is decimal digits or the literal `####` sequence placeholder. The sample frame is `2048`; other digit widths also pass. Parsing a placeholder does not enumerate files on disk.
- Camera descriptors start lowercase and contain letters or digits, allowing labels such as `threeQuarter`. Roles are examples rather than an exhaustive enum. Bare version descriptors and appended version tokens are rejected.
- Render and publish locations are relative task paths. Assets and shots share the same folder layout, and the version folder omits the render descriptor. Job roots, entity hierarchy paths, and workfile locations are outside this example.
- Reader handlers and extension vocabularies belong to the host application. This example does not configure them; the package's reader registry remains available for that purpose.

Run `uv run pytest tests/test_name_cases.py -k studio -v` to check every studio table row.
