# Studio naming example

[studio.names](studio.names) is a draft transcription of a studio naming conventions document. It is an executable example for reviewing that page's rules, not an approved production configuration. The source page's update date is a placeholder, and its linked Codes and Folder Structure pages were not supplied.

The templates come first, followed by reusable field rules. Optional tags, job suffixes, and frame components currently use separate resource definitions because Namespec does not yet support optional template groups.

## Editable examples

Each CSV contains exact names, expected types, extracted metadata in separate columns, and explanations. Additional edge cases supplement the examples quoted by the source.

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

A basename can match more than one convention. `prop_Lantern_mdl_model_v017.abc` fits both an asset render and a published output. The relative `work/.../renders/...` or `pub/.../outputs/...` path distinguishes them. Likewise, `731_037` could be a sequence or a job folder; `NVA_086` could be a sequence or an asset until an authoritative asset-type vocabulary narrows the possibilities.

`inspect()` returns every match. `parse()` requires a resource hint when multiple matches remain. The CSV `matches` column explicitly lists all expected interpretations, so a future change that accidentally hides or introduces a match fails the tests. `resource` identifies the interpretation whose metadata the row checks.

## Draft choices and unresolved source details

- The job section shows `68219_MoonOrchard` but labels the descriptor required. This draft accepts both documented forms. That is a working interpretation, not a settled Studio policy.
- The asset hierarchy lists `{type}_{Descriptor}` but illustrates a longer name with task and version. `asset` represents the short identity; `asset_version` represents the longer example.
- The broad rule calls the descriptor optional without defining every descriptor-free entity form. This draft covers the concrete asset and shot structures shown on the page; it does not claim exhaustive coverage of that optional form.
- Asset types and tasks use letter-only tokens as an initial assumption based on the examples. Most other tokens use ASCII alphanumeric text. These are syntax checks, not authoritative code lists; the Codes page may require different rules. The `.ma` example is preserved as supplied source data and does not add any DCC tooling.
- Episode, sequence, shot, job number, and version stay text to preserve their exact spelling, including zeroes. Sequence and shot widths are explicitly three and four digits. This draft reads `v###` as exactly three digits; whether `v000` is permitted or versions can exceed `v999` is not settled by the page. Consequently `000` currently passes the syntax rule and `1000` does not. This differs from the minimum-width integer example in `assets.names`.
- A frame is either decimal digits or the literal `####` sequence placeholder shown in the docs. Actual frame width and other placeholder formats are unspecified. Parsing a placeholder does not enumerate files on disk.
- Camera descriptors start lowercase and contain letters/digits. This approximates the stated camelCase convention; it does not determine word boundaries. Suggested roles are examples rather than an exhaustive enum. Bare version descriptors and appended version tokens are rejected.
- Render and publish locations are relative task paths from the page. Applying those templates to shots is an extrapolation from its general entity rule, covered by additional test examples. No job root, entity hierarchy path, or workfile location is invented. The version folder omits the render descriptor, matching the supplied examples.
- Reader mappings are unspecified: the page does not define handler IDs or a complete extension vocabulary. The package's reader registry remains available for a host application to configure.

Run `uv run pytest tests/test_name_cases.py -k studio -v` to check every Studio table row.
