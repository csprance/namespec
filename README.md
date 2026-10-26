# Namespec

Write your studio's naming rules once, in a small text file anyone can read. Every tool then uses that same file to check a name, take it apart, and build the next one. Pure Python, no dependencies, errors that say which part is wrong. MIT licensed.

```powershell
uv sync
uv run namespec examples/guide.names inspect Donut_high_v004.abc
```

The rest of this page builds [examples/guide.names](examples/guide.names) one idea at a time. By the end you can write your own.

## 1. A name is a sentence with blanks

`Donut_high_v004.abc` is an asset, a level of detail, a version and a file type, glued together with underscores and a dot. Write the glue as text and the parts as blanks:

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

A `resource` is one kind of name. Its `name` is the template. Each `{blank}` refers to a field declared above. Ask what a name is:

```powershell
uv run namespec rules.names inspect Donut_high_v004.abc
```

It prints JSON. The lines that matter:

```text
"status": "valid"
"resource": "model"
"fields": {"asset": "Donut", "lod": "high", "version": 4, "ext": "abc"}
```

The version came back as the number 4, not the text `004`. That is the whole idea. Everything below is detail.

## 2. Blanks have rules

Three kinds of field cover almost everything:

| field | means |
| --- | --- |
| `text matching "[A-Z][a-z]+"` | a regular expression the value must fit |
| `one of "low", "mid", "high"` | exactly one of these spellings |
| `integer minimum 1 padded to 3 digits` | a number, written with at least three digits |

A wrong name does not just fail. The rules say which blank is wrong and keep the parts that were fine:

| name | result |
| --- | --- |
| `Donut_ultra_v004.abc` | `invalid_field` on `lod`: expected low, mid or high. asset, version and ext still returned |
| `Donut_high_v4.abc` | `noncanonical_field` on `version`: 4 must be written `004` |
| `donut_high_v004.abc` | `invalid_field` on `asset`: must start with a capital |
| `Donut_high.abc` | `pattern_mismatch`: the version blank is missing, nothing to assign |

`examples "Donut"` on a text field is not a whitelist. It is a sample the tool can use to generate names, and a hint to the next reader.

## 3. Prove it, right there

Put the names you care about under the resource. They are tests, and a producer can read them.

```text
example model {
    input = "Donut_high_v004.abc"
    expect { asset = "Donut" lod = "high" version = 4 ext = "abc" }
}
reject model { input = "Donut_ultra_v004.abc" expect = "invalid_field" }
reject model { input = "Donut_high_v4.abc" expect = "noncanonical_field" }
```

```powershell
uv run namespec rules.names test
```

An `example` must produce exactly those fields, with those types. A `reject` must produce that error code. When someone changes a rule, the examples say what broke.

## 4. Where it lives

A location is a template too. `{name}` stands for the filename from above.

```text
job = text matching "[a-z0-9]+" examples "show17"

resource model {
    name     = "{asset}_{lod}_v{version}.{ext}"
    location = "/jobs/{job}/assets/{asset}/{lod}/{name}"
}
```

Parse a full path with `--source location` and you get `job` as well. Because `asset` appears in the folder and in the filename, the two must agree:

```text
/jobs/show17/assets/Chair/high/Donut_high_v004.abc
conflicting_field on asset: folder says Chair, file says Donut
```

Going the other way, a basename knows nothing about the job, so you supply it:

```python
catalog.parse("Donut_high_v004.abc").locate(job="show17")
# "/jobs/show17/assets/Donut/high/Donut_high_v004.abc"
```

Once roots exist in the next step, pass `root="mac"` the same way.

## 5. Roots

Jobs are mounted somewhere different on every platform. Declare the prefixes once and start the location with `{root}`:

```text
roots {
    mac     = "/Volumes/jobs"
    windows = "J:/jobs"
}

resource model {
    name     = "{asset}_{lod}_v{version}.{ext}"
    location = "{root}/{job}/assets/{asset}/{lod}/{name}"
}
```

A path under either root parses, and `root` comes back holding the one it used. When building a path, say `root="windows"` or give the prefix itself. A path under any other prefix is simply not a model.

## 6. Names made of names

A shot code like `101_120_0040` is an episode, a sequence number and a shot number. Say so:

```text
Episode  = text matching "[0-9]+" examples "101"
seqnum   = text matching "[0-9]+" examples "120"
shotnum  = text matching "[0-9]+" examples "0040"
Sequence = "{Episode}_{seqnum}"
Shot     = "{Sequence}_{shotnum}"
Task     = one of "comp", "anim", "light"
scene_ext = one of "nk", "ma"

resource scene {
    name     = "{Shot}_{Task}_v{version}.{scene_ext}"
    location = "{root}/{job}/shots/{Episode}/{Sequence}/{Shot}/{Task}/{name}"
}
```

A field written as a template is a composite. Parsing `101_120_0040_comp_v003.nk` gives you the whole and the parts: `Shot`, `Sequence`, `Episode`, `seqnum`, `shotnum`. Errors point inside: a shot folder `101_125_0040` under the sequence folder `101_120` is a `conflicting_field` on `seqnum`, not a vague "no match". When you build a name you may give `Shot="101_120_0040"` or the parts, whichever you have.

You could instead write one flat rule, `text matching "[0-9]+_[0-9]+_[0-9]+"`, and it works. You just lose the parts and the pointed errors.

## 7. Sometimes a piece is missing

Artists add their initials to a scene now and then. Square brackets mark a part that may be absent:

```text
tag = text matching "[a-z]+" examples "jm"

resource scene {
    name = "{Shot}_{Task}_v{version}[_{tag}].{scene_ext}"
}
```

Both `101_120_0040_comp_v003.nk` and `101_120_0040_comp_v003_jm.nk` are scenes. When the tag is absent it is not in the fields at all. When you build a name without a `tag`, the bracket disappears. A group must start or end with punctuation, so there is never a doubt where it begins.

## 8. Folders are resources too

Tools need "the task folder" as often as they need a file. A resource with a location and no name is a folder:

```text
resource task_folder {
    location = "{root}/{job}/shots/{Episode}/{Sequence}/{Shot}/{Task}"
}
```

It parses and builds with `source="location"`, and it is never mistaken for a basename.

## 9. Paths pasted from Windows

```text
normalize {
    slashes = "forward"
    drive   = "upper"
}
```

With this block, `j:\jobs\show17\shots\...` is read as `J:/jobs/show17/shots/...` before matching. Only locations are touched, only in these two ways, and the text length never changes, so error positions still point at the original. Without the block, nothing is ever altered.

## 10. Extra facts for tools

```text
resource scene {
    name     = "{Shot}_{Task}_v{version}[_{tag}].{scene_ext}"
    location = "{root}/{job}/shots/{Episode}/{Sequence}/{Shot}/{Task}/{name}"
    meta { entities = ["Episode", "Sequence", "Shot", "Task"] kind = "workfile" }
}
```

`meta` is data for whoever is reading. Matching ignores it. A publisher looks at `entities` to know which ShotGrid records a path implies; a browser looks at `kind`. Strings, integers and lists of either.

## 11. From Python

```python
from namespec import Catalog

catalog = Catalog.from_file("examples/guide.names")

path = "/Volumes/jobs/show17/shots/101/101_120/101_120_0040/comp/101_120_0040_comp_v003.nk"
scene = catalog.parse(path, source="location")
scene.kind  # "scene"
scene.fields["Shot"]  # "101_120_0040"
scene.fields["version"]  # 3
scene.metadata["kind"]  # "workfile"

# Build related paths from what you parsed. Keyword arguments win over the mapping.
catalog.locate("render", scene.fields, frame="####", image_ext="exr")
# ".../101_120_0040/comp/renders/v003/101_120_0040_comp_v003.####.exr"
catalog.format("scene", scene.fields, version=4)
# "101_120_0040_comp_v004.nk"
catalog.locate("task_folder", scene.fields)
# ".../101_120_0040/comp"

# Check without raising.
result = catalog.validate("Donut_ultra_v004.abc", "model")
result.valid  # False
result.diagnostics[0].code  # "invalid_field"
result.diagnostics[0].field  # "lod"
result.fields  # {"asset": "Donut", "version": 4, "ext": "abc"}

catalog.inspect("101_120_0040_comp_v003.nk").status  # "valid"; lists every resource that fits
catalog.validate_field("Shot", "101_120_0040").valid  # True; one field on its own
list(catalog.samples("model", limit=3))
# ["Donut_low_v001.abc", "Donut_low_v001.usd", "Donut_low_v002.abc"]
```

`parse` raises `NameSpecError` with the same diagnostics when a name is wrong or fits more than one resource. Pass the resource name when you already know it: `catalog.parse(text, "scene")`. Paths may be `pathlib` objects.

## 12. Teach it your studio's tricks

Rule files describe names. What your studio *does* with a path, open it, find the next version, look it up in ShotGrid, is Python. Put those methods on a class and bind it to the resources it serves:

```python
from namespec import Catalog, Resource

catalog = Catalog.from_file("examples/guide.names")


@catalog.resource("scene")
class Scene(Resource):
    def render_path(self, frame="####", image_ext="exr"):
        return self.catalog.locate("render", self.fields, frame=frame, image_ext=image_ext)

    def next_version(self):
        return self.catalog.format("scene", self.fields, version=self.fields["version"] + 1)


scene = catalog.parse(path, source="location")  # now a Scene
scene.render_path()
scene.next_version()  # "101_120_0040_comp_v004.nk"
```

`catalog.resource` takes names or patterns like `"shot_*"`. Share methods through ordinary inheritance. Anything you leave unbound comes back as a plain `Resource`. Nothing about these classes is in the rules file.

## 13. Everywhere a name is written or read

One file, loaded the same way by every tool:

```python
from namespec import load_rules

catalog = load_rules("STUDIO_NAMES", default="examples/guide.names")
```

`load_rules` reads the file an environment variable names, falls back to the default, and remembers the result for the process. Set the variable in your DCC launcher and every tool agrees on the rules. Ship the `.names` file next to your code; there is nothing else to install.

- A save dialog validates the name before writing it.
- A publisher parses the scene path and derives the render and the ShotGrid entities from `meta`.
- A browser lists a folder, parses each basename with the resource it expects, and shows the versions.
- A render farm checks every output path it is handed.
- `namespec rules.names export --output rules.json` hands the same rules to a tool in another language.

## 14. Write your own

1. Collect five real paths. Underline the parts that change.
2. Write one `resource` per kind of path. Glue is text, parts are `{blanks}`.
3. Declare each blank: `one of` when there is a list, `integer` when it counts, `text matching` otherwise. Give text fields an `examples`.
4. Paste your five paths in as `example` blocks. Add a `reject` for the mistake you see most.
5. Run `namespec rules.names test` until it passes. Then `inspect` a few names you are unsure about.
6. Reach for composites when a part has parts, brackets when a part comes and goes, a folder resource when a tool wants a directory.

[examples/studio.names](examples/studio.names) is a larger fictional convention written this way, with [CSV tables](tests/cases/README.md) of expected answers beside it. [docs/reference.md](docs/reference.md) lists every construct, every error code and the Python API. [editors/vscode](editors/vscode/README.md) has syntax highlighting and go-to-definition for `.names` files.
