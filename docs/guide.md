# Namespec: from your first rule to a shared naming system

Use Namespec when a save dialog, publisher, browser, or farm tool needs to agree on what a filename means and where it belongs. One `.names` file defines the convention; each tool uses it to check input, read fields, and build the next name or path.

Start by [using an existing catalog](#use-an-existing-catalog-first). If you own the convention, continue into writing rules. You need no regex knowledge to use a catalog. The runnable companions are [guide.names](../examples/guide.names) and [advanced.names](../examples/advanced.names); the [reference](reference.md) covers exact syntax and API details.

Jump to the part your tool needs:

- [Get set up](#1-get-a-working-setup), [write a rule](#2-write-your-first-rule), and [run its tests](#4-keep-examples-beside-the-rules).
- [Use Python](#5-use-the-same-rules-from-python), [add locations](#6-add-a-location), and [share roots](#7-share-rules-across-machines).
- [Use composites](#9-describe-names-that-have-parts), [optional groups](#10-make-a-piece-optional), and [related paths](#11-work-with-folders-metadata-and-related-paths).
- [Replace values](#12-change-a-parsed-resource-safely), [check roundtrips](#13-check-that-generated-values-survive-parsing), and [validate filesystem spelling](#14-opt-into-filesystem-spelling-checks).
- [Add classes](#17-add-behavior-with-an-ordinary-python-class), [register readers](#18-register-readers-when-a-tool-needs-them), and [share the convention](#19-load-one-shared-convention-across-tools).
- [Build your own and troubleshoot](#20-build-your-own-convention).

## 1. Get a working setup

You need Git and [uv](https://docs.astral.sh/uv/getting-started/installation/). Namespec requires Python 3.10 or newer; uv can download a compatible interpreter if needed. Use PowerShell on Windows, or bash/zsh on Linux and macOS. Git Bash on Windows can rewrite paths such as `/jobs/...` when passing them to Python; use PowerShell for these exercises, or disable that conversion with `MSYS_NO_PATHCONV=1`.

If you already have this repository open, open a terminal in its root, the folder containing `pyproject.toml`. Otherwise:

```console
git clone https://github.com/csprance/namespec.git
cd namespec
```

Create the project environment and check that the shipped rules work:

```console
uv sync --locked
uv run --locked namespec examples/guide.names test
```

Expected result:

```text
9 passed
```

Run all commands in this guide from that repository root. `uv run` uses its Python environment, so you do not need to activate it. See uv's [project guide](https://docs.astral.sh/uv/guides/projects/) for the environment workflow.

There are three kinds of code below:

| Kind | Where it goes |
| --- | --- |
| Terminal commands beginning with `uv` | Your terminal |
| Naming rules beginning with `spec 1` or a declaration | A plain text `.names` file |
| Python beginning with `from namespec import ...` | A `.py` script, run with `uv run --locked python script.py` |

No VS Code extension is required. If you want highlighting, inline errors, navigation, and example run buttons, follow the [editor setup](../editors/vscode/README.md) after this first check.

### Use an existing catalog first

If your team already has a `.names` file, load it and inspect its choices. This example uses the shipped catalog to build the next version's output path. Save it as `use_catalog.py` and run `uv run --locked python use_catalog.py`:

```python
from namespec import Catalog

catalog = Catalog.from_file("examples/guide.names")
print(list(catalog.resources))  # model, scene, render, task_folder
print(catalog.roots)  # Root labels mapped to their path prefixes.

model = catalog.parse("Donut_high_v004.abc")
print(model["version"])  # 4
print(list(model.keys()))  # The fields this input supplied.
print(model.missing_context)  # ('root', 'job')

located = model.with_context(root="windows", job="show17")
print(located.replace(version=5).path.as_posix())
# J:/jobs/show17/assets/Donut/high/Donut_high_v005.abc
```

`model`, `scene`, and the root label `windows` come from this catalog. Your team's file can define different kinds, fields, and roots; discover them with `catalog.resources`, `catalog.fields`, and `catalog.roots`. `keys()` shows what a parsed resource contains, and `missing_context` tells you what its location still needs. These operations build and validate paths without creating files.

`source` is a separate built-in choice: its values are always `"auto"`, `"name"`, and `"location"`. The default `"auto"` accepts either a filename or a location, so this workflow needs no source argument. See [when to select a source](reference.md#when-to-select-a-source) when your tool must require one form.

To use your team's convention, change the catalog filename and sample input, then choose values from that catalog. To define your own, continue below.

## 2. Write your first rule

Write a rule when you own the convention and want every tool to enforce it. In `Donut_high_v004.abc`, the changing values are asset, level of detail, version, and file type; underscores, `v`, and the dot separate them.

Create `rules.names` beside `pyproject.toml`. Save it as UTF-8 plain text, with the exact extension `.names`, and paste:

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

`spec 1` declares the language version. A **field** is a named value with a rule. A **template** combines fields in `{braces}` with literal text. A **resource** describes one kind of name or path; here, that kind is called `model`.

Inspect a name:

```console
uv run --locked namespec rules.names inspect Donut_high_v004.abc
```

The command prints JSON. Among its results are these values, shown here as an excerpt:

```text
"status": "valid"
"resource": "model"
"fields": {"asset": "Donut", "lod": "high", "version": 4, "ext": "abc"}
```

Parsing turns text into typed values. The version is the integer `4`. Formatting goes the other way and writes it as `004`.

## 3. Understand the fields and errors

Choose field types to express what users may enter and what tools receive back:

| Declaration | Meaning |
| --- | --- |
| `text matching "[A-Z][a-z]+"` | One uppercase letter followed by one or more lowercase letters |
| `one of "low", "mid", "high"` | Exactly one of these spellings, including case |
| `integer minimum 1 padded to 3 digits` | An integer at least 1, written with at least three digits |

A text regex must match the whole field. `Donut` and `Chair` both fit this one; `donut`, `DONUT`, and `Donut2` do not. Choose a pattern that fits your real asset identifiers.

`examples "Donut"` provides a sample for generated names. It does not limit valid values to that sample. Use `one of` for an allowed list.

Keep identifiers such as shot number `0040` as text when their leading zeros are part of their identity. Use integers for counts and versions where arithmetic matters.

Try changing the input to the inspect command:

| Input | Result |
| --- | --- |
| `Donut_ultra_v004.abc` | `invalid_field` on `lod` |
| `Donut_high_v4.abc` | `noncanonical_field` on `version`: it must be written `004` |
| `donut_high_v004.abc` | `invalid_field` on `asset` |
| `Donut_high.abc` | `pattern_mismatch`: the required shape is missing |

Diagnostics may include the fields that could be recovered. Treat these as provisional until validation succeeds; an invalid input is not a trusted resource.

## 4. Keep examples beside the rules

Examples catch convention changes that would break existing names. Append these checks to `rules.names`, with one blank line after its closing brace:

```text
example model {
    input = "Donut_high_v004.abc"
    expect { asset = "Donut" lod = "high" version = 4 ext = "abc" }
}
reject model { input = "Donut_ultra_v004.abc" expect = "invalid_field" }
reject model { input = "Donut_high_v4.abc" expect = "noncanonical_field" }
```

Run them:

```console
uv run --locked namespec rules.names test
```

```text
3 passed
```

An `example` checks the complete field dictionary, including types. A `reject` checks that the input fails with the named diagnostic code.

Temporarily change `"high"` to `"hi"` in the `lod` declaration, leaving the examples alone. Run the test command again:

```text
rules.names:13:13: example model: Not a valid model: Invalid 'lod'; expected one of ('low', 'mid', 'hi').
2 passed, 1 failed
```

The line and column point at the example input. Your line number will differ if you added comments or blank lines. A wrong expected value is also located precisely, with a message such as `Expected lod = "mid", got "high".`

**Restore `"high"` before continuing**, then confirm all three tests pass. Use `test --json` when another tool needs structured results. Exit status is 0 for success, 1 for a failed check, and 2 for a command or definition error.

## 5. Use the same rules from Python

Use the catalog in your save or publish tool to avoid repeating the naming rules in Python. A **Catalog** loads the definitions; a parsed **Resource** provides typed fields and methods for building names and paths.

Save this complete script as `inspect_model.py` beside `rules.names`:

```python
from namespec import Catalog

catalog = Catalog.from_file("rules.names")
model = catalog.parse("Donut_high_v004.abc")

print(model.kind)
print(model["version"])
print(model.replace(version=5).name)
```

Run it:

```console
uv run --locked python inspect_model.py
```

Expected output:

```text
model
4
Donut_high_v005.abc
```

A resource behaves like a read-only field dictionary: use `model["version"]`, `model.get("tag")`, `model.keys()`, or `model.items()`. `replace` returns a new validated resource; its `name` is a string. The original remains unchanged. You can still generate a name without parsing one first: `catalog.format("model", asset="Donut", lod="high", version=5, ext="abc")`.

Use `parse` when a failure should raise `NameSpecError`. Use `validate` for a form or dialog that needs to display errors:

```python
from namespec import Catalog

catalog = Catalog.from_file("rules.names")
result = catalog.validate("Donut_ultra_v004.abc", "model")
print(result.valid)  # False
print(result.diagnostics[0].code)  # invalid_field
print(result.diagnostics[0].field)  # lod
```

Use `catalog.inspect(text)` when you need to discover a kind or explain why nothing fits. It reports `valid`, `invalid`, or `ambiguous`; `parse(text)` raises if multiple interpretations fit. Supply the catalog's kind, such as `"model"`, when your tool already knows it.

Leave `source="auto"` for ordinary parsing. Use `source="name"` in a filename-only save dialog, or `source="location"` when checking the complete folder layout, so a valid basename alone cannot pass. Selecting a source can also resolve rare name/location ambiguities. See [when to select a source](reference.md#when-to-select-a-source) for examples.

## 6. Add a location

Add a location when tools need to agree on the folders as well as the filename. In `rules.names`, add this field once, above the resource:

```text
job = text matching "[a-z0-9]+" examples "show17"
```

**Replace the existing `resource model` block** with this version. Keep the other declarations and examples:

```text
resource model {
    name     = "{asset}_{lod}_v{version}.{ext}"
    location = "/jobs/{job}/assets/{asset}/{lod}/{name}"
}
```

`{name}` expands the resource's filename template. Inspect a complete path with the same command:

```console
uv run --locked namespec rules.names inspect /jobs/show17/assets/Donut/high/Donut_high_v004.abc
```

This also returns `job="show17"`. Repeated fields must agree: `/jobs/show17/assets/Chair/high/Donut_high_v004.abc` fails with `conflicting_field` on `asset`.

A basename has no job information. `missing_context` tells you what the location needs; `with_context` supplies it and returns a resource with the complete location:

```python
from namespec import Catalog

catalog = Catalog.from_file("rules.names")
model = catalog.parse("Donut_high_v004.abc")
print(model.path.as_posix())  # Donut_high_v004.abc
print(model.missing_context)  # ('job',)
located = model.with_context(job="show17")
print(located.path.as_posix())
# /jobs/show17/assets/Donut/high/Donut_high_v004.abc
print(located["job"])  # show17
```

Reload the catalog after editing a rule file. It is a compiled snapshot, not a file watcher. `path` and `locate()` return native `pathlib.Path` objects; call `.as_posix()` for consistent forward-slash display on every platform. `model.locate(job="show17")` is convenient when you only need the path. Neither operation creates directories, checks existence, or searches for files.

`with_context` needs enough information to resolve the full location. It validates the result and leaves the original basename resource unchanged. Its `source` is still `"name"`; the returned resource's `source` is `"location"`.

## 7. Share rules across machines

Declare roots when the same files live under different mount prefixes on different machines. Add these blocks once, after `spec 1` in `rules.names`:

```text
roots {
    mac     = "/Volumes/jobs"
    windows = "J:/jobs"
}

normalize {
    slashes = "forward"
    drive   = "upper"
}
```

Change just the model's `location` line to:

```text
    location = "{root}/{job}/assets/{asset}/{lod}/{name}"
```

A root is a declared prefix. Its label, such as `windows`, is convenient for generation. A parsed resource exposes that label as `root_name` and its prefix as a `Path` in `root`. The field dictionary also keeps the prefix string under `"root"`.

```python
from namespec import Catalog

catalog = Catalog.from_file("rules.names")
model = catalog.parse("Donut_high_v004.abc")
print(model.locate(root="windows", job="show17").as_posix())
# J:/jobs/show17/assets/Donut/high/Donut_high_v004.abc

located = catalog.parse("J:/jobs/show17/assets/Donut/high/Donut_high_v004.abc")
print(located.root.as_posix())  # J:/jobs
print(located.root_name)  # windows
```

The normalization block accepts pasted Windows separators and uppercases an ASCII drive letter. Try this in PowerShell:

```powershell
uv run --locked namespec rules.names inspect 'j:\jobs\show17\assets\Donut\high\Donut_high_v004.abc'
```

Normalization applies only to locations. It does not lowercase field values, resolve `..`, or alter arbitrary punctuation. Without the block, input strings are matched as written. `pathlib` objects already have their own path representation, so use the original string when its exact spelling matters.

Roots must be nonempty, use forward slashes, and have no trailing slash. Two roots may not collapse to the same prefix after normalization.

## 8. Move to the complete companion

You now have a working small convention. Keep `rules.names` as your exercise.

For the rest of the guide, use **`examples/guide.names`**. It already contains every declaration shown in the next sections, plus nine executable examples. The fragments explain that file; do not append them to it or duplicate its declarations.

```console
uv run --locked namespec examples/guide.names test
```

Each Python block below starts by loading the file it uses. You can save any complete block as a script in the repository root and run it with `uv run --locked python script.py`.

## 9. Describe names that have parts

Use a composite when tools need both a whole identifier and its parts. A shot code such as `101_120_0040` can identify a shot while also supplying episode and sequence folders:

```text
Episode  = text matching "[0-9]+" examples "101"
seqnum   = text matching "[0-9]+" examples "120"
shotnum  = text matching "[0-9]+" examples "0040"
Sequence = "{Episode}_{seqnum}"
Shot     = "{Sequence}_{shotnum}"
```

A field declared as a template is a **composite**. The companion's scene template uses `{Shot}`. Parsing exposes `Shot`, `Sequence`, `Episode`, `seqnum`, and `shotnum`:

```python
from namespec import Catalog

catalog = Catalog.from_file("examples/guide.names")
scene = catalog.parse("101_120_0040_comp_v003.nk")
print(scene["Shot"])  # 101_120_0040
print(scene["Sequence"])  # 101_120
print(scene["shotnum"])  # 0040

print(catalog.format("scene", Shot="101_120_0040", Task="comp", version=3, scene_ext="nk"))
print(
    catalog.format(
        "scene",
        Episode="101",
        seqnum="120",
        shotnum="0040",
        Task="comp",
        version=3,
        scene_ext="nk",
    )
)
# Both calls produce 101_120_0040_comp_v003.nk.
```

You can supply a whole composite or its parts. If you supply both, they must agree. A shot folder `101_125_0040` inside sequence folder `101_120` produces a `conflicting_field` error on `seqnum`.

Names and field identifiers are case sensitive: `Task` and `task` are different identifiers. Include derived composites in an inline example's `expect` dictionary, since it checks every returned field.

## 10. Make a piece optional

Use an optional group when one kind of resource permits both forms, such as scenes with or without an artist tag:

```text
tag = text matching "[a-z]+" examples "jm"

resource scene {
    name = "{Shot}_{Task}_v{version}[_{tag}].{scene_ext}"
    location = "{root}/{job}/shots/{Episode}/{Sequence}/{Shot}/{Task}/{name}"
    meta { entities = ["Episode", "Sequence", "Shot", "Task"] kind = "workfile" }
}
```

Square brackets mark an optional group. Both `101_120_0040_comp_v003.nk` and `101_120_0040_comp_v003_jm.nk` parse. An absent `tag` is omitted from the returned fields; it is not an empty string.

```python
from namespec import Catalog

catalog = Catalog.from_file("examples/guide.names")
plain = catalog.parse("101_120_0040_comp_v003.nk")
tagged = plain.replace(tag="jm")
print(tagged.name)  # 101_120_0040_comp_v003_jm.nk
print(tagged.replace(tag=None).name)  # 101_120_0040_comp_v003.nk
```

An optional group must contain a field and have punctuation at one edge. Groups cannot nest. A group such as `[_{artist}_{purpose}]` needs both values once either is supplied. Its punctuation provides structure, but overlapping field patterns can still leave more than one possible division of the text. Prefer fields that do not consume their separators.

## 11. Work with folders, metadata, and related paths

Derive output paths from a scene so job, shot, task, and version stay consistent. A location-only resource lets the same rules describe its containing folder:

```text
resource task_folder {
    location = "{root}/{job}/shots/{Episode}/{Sequence}/{Shot}/{Task}"
}
```

Pass its path to `catalog.parse` just like a filename. It has no basename to format or sample. Use `related` to carry a parsed resource's context into another kind.

The scene's `meta` block tells host tools facts such as its workfile role and entity hierarchy. Metadata accepts strings, integers, and lists, returned as a copy with lists exposed as tuples. It does not affect matching or change when fields change.

Use the context from a scene path to build related outputs:

```python
from namespec import Catalog

catalog = Catalog.from_file("examples/guide.names")
path = "/Volumes/jobs/show17/shots/101/101_120/101_120_0040/comp/101_120_0040_comp_v003.nk"
scene = catalog.parse(path)
print(scene.metadata["kind"])  # workfile
print(scene.metadata["entities"])  # ('Episode', 'Sequence', 'Shot', 'Task')

folder = scene.related("task_folder")
print(folder.path.as_posix())
# /Volumes/jobs/show17/shots/101/101_120/101_120_0040/comp

render = scene.related("render", frame="####", image_ext="exr")
print(render.path.as_posix())
# /Volumes/jobs/show17/shots/101/101_120/101_120_0040/comp/renders/v003/101_120_0040_comp_v003.####.exr
print(render["frame"])  # ####
```

Here `frame` is a text field accepting four digits or `####`. The placeholder remains literal text; Namespec does not expand an image sequence. A DCC or host application gives it that meaning. If your tools also use `%04d`, add that spelling to the field's regex and its examples.

`related` uses the target's location when it has one, otherwise its filename. It requires enough context for that template, accepts explicit field overrides, and returns the target's registered resource class. For direct generation from a dictionary, `catalog.locate("render", fields, frame="####", image_ext="exr")` returns a `Path`.

When changing a composite's part, replace it before deriving the output: `scene.replace(shotnum="0041").related("render", frame="####", image_ext="exr")`. `replace` recomputes the inherited `Shot` and `Sequence` values; `related` checks that supplied whole and part values agree.

## 12. Change a parsed resource safely

Use `replace` to change a version or shot without leaving stale composite values behind:

```python
from namespec import Catalog

catalog = Catalog.from_file("examples/guide.names")
scene = catalog.parse("101_120_0040_comp_v003.nk")
next_shot = scene.replace(shotnum="0041", version=4)

print(next_shot.name)  # 101_120_0041_comp_v004.nk
print(next_shot["Shot"])  # 101_120_0041
print(scene.name)  # 101_120_0040_comp_v003.nk
```

The original stays unchanged. Parent composites are recomputed and the new text must parse back to the requested values. Replacing a whole composite updates its parts; explicitly conflicting whole and part replacements still fail.

You may only replace fields belonging to the source you parsed. A scene parsed from its basename has no `job` or `root`; use `located = scene.with_context(job="show17", root="mac")` to add them. `located.replace(version=4)` keeps that location context, and `located.replace(root="windows")` moves to another declared root. A scene parsed from a location can replace location fields too.

`scene.locate(**context)` and `scene.with_context(**context)` reject context that disagrees with parsed values. For an intentional destination change, use `replace` on a located resource. Use `related` to derive a different kind of resource.

A fresh `scene.fields` dictionary is returned each time. Editing that dictionary does not mutate the resource. Passing a changed child alongside stale composite values to `catalog.format` is a conflict; `replace` handles that recomputation for you.

## 13. Check that generated values survive parsing

If two adjacent fields both accept their separator, a generated name may parse with a different split. The default parser makes a deterministic choice, but that choice may lose the values you meant.

This standalone Python example deliberately uses overlapping patterns:

```python
from namespec import Catalog, NameSpecError

rules = """
spec 1
left = text matching "[a-z_]+"
right = text matching "[a-z_]+"
resource pair { name = "{left}_{right}" }
"""
catalog = Catalog.from_string(rules, strict=True)

try:
    catalog.format("pair", left="a", right="b_c")
except NameSpecError as error:
    print(error.diagnostics[0].code)  # non_roundtripping_value
```

`strict=True` checks generated names, locations, and samples against the intended values. `Resource.replace` always performs this check. Strict mode does not prove that every input has only one possible split. Design field patterns around your separators and add representative examples.

Regexes use Python `re` semantics. Anchors, inline flags, lookarounds, and backreferences are supported within individual fields; advanced patterns do not refer to other fields' capture groups. See [matching policies in the reference](reference.md#matching-and-generation-policies) before relying on subtle matching behavior.

## 14. Opt into filesystem spelling checks

A valid studio name can still be an invalid operating-system filename. Install the optional validator in this checkout:

```console
uv sync --locked --extra filesystem
```

Save this as `check_filesystem.py`:

```python
from namespec import Catalog

catalog = Catalog.from_string(
    """
    spec 1
    stem = text matching "[A-Z]+"
    resource document { name = "{stem}.txt" }
    """,
    filesystem="portable",
)
result = catalog.validate("CON.txt", "document")
print(result.valid)  # False
print(result.diagnostics[0].code)  # unsafe_path
```

Run with the extra enabled:

```console
uv run --locked --extra filesystem python check_filesystem.py
uv run --locked --extra filesystem namespec examples/guide.names --filesystem portable test
```

Use `portable` for names shared with Windows, or `windows` / `posix` for one platform. All policies reject `.` and `..` components, ASCII controls, and components longer than 255 UTF-8 bytes. Windows and portable policies also reject reserved device names, forbidden characters, and trailing spaces or dots.

These checks validate spelling. They do not check existence, permissions, symlink destinations, or the total path length. Use the original input string if dot components must be detected before `pathlib` normalizes them. The default catalog has no filesystem policy and no runtime dependencies.

CLI catalog options go **before the subcommand**: `namespec rules.names --strict inspect ...` or `namespec rules.names --filesystem portable test`. Keep `--extra filesystem` on subsequent `uv run` commands that use a policy.

## 15. Handle signed frames and literal punctuation

Use signed integers for frames before zero, bounds for a permitted range, and escapes for literal template punctuation. The separate [advanced companion](../examples/advanced.names) demonstrates these cases:

```console
uv run --locked namespec examples/advanced.names test
```

Expected result: `4 passed`.

Its frame declaration is:

```text
frame = integer minimum -100 maximum 9999 padded to 4 digits
```

The limits are inclusive. `-1` formats as `-0001`; the sign does not count toward padding. `+0001` and `-0000` are not canonical spellings. Without a maximum, values can grow beyond the padding width: three digits is a minimum, not a limit of 999.

This frame definition is an alternative to the text placeholder field in `guide.names`. Do not add a second declaration of `frame` to the same file.

For literal brackets, double them: `"[[{asset}]]"` produces `[Sky_Depot]`. For literal braces, use `{{` and `}}`. An escaped `{{name}}` stays literal text instead of expanding a filename.

## 16. Generate examples to inspect your design

Generate sample names to review a convention before distributing it. Check or format one field when a form edits that value separately:

```python
from namespec import Catalog

catalog = Catalog.from_file("examples/guide.names")
for name in catalog.samples("model", limit=3):
    print(name)
# Donut_low_v001.abc
# Donut_low_v001.usd
# Donut_low_v002.abc

print(catalog.validate_field("Shot", "101_120_0040").valid)  # True
print(catalog.format_field("version", 6))  # 006
```

`samples` uses enum members, integer candidates, and explicitly authored text examples. It does not invent text from a regex. Supply samples on text fields or pass explicit overrides such as `asset="Chair"`. Optional groups are generated as complete units.

Keep tests based on real production names and known mistakes alongside these samples.

## 17. Add behavior with an ordinary Python class

Bind a class when several tools need the same actions on a resource, such as deriving renders or asking ShotGrid about a shot. Those methods can use the parsed fields directly:

Save this complete script as `scene_tools.py`:

```python
from namespec import Catalog, Resource

catalog = Catalog.from_file("examples/guide.names")


@catalog.resource("scene")
class Scene(Resource):
    def render_path(self, frame="####", image_ext="exr"):
        return self.related("render", frame=frame, image_ext=image_ext).path

    def next_version(self):
        return self.replace(version=self["version"] + 1)


path = "/Volumes/jobs/show17/shots/101/101_120/101_120_0040/comp/101_120_0040_comp_v003.nk"
scene = catalog.parse(path)
print(isinstance(scene, Scene))  # True
print(scene.render_path().as_posix())
print(scene.next_version().name)  # 101_120_0040_comp_v004.nk
```

Run it with `uv run --locked python scene_tools.py`. Replacements preserve the bound subclass.

Bindings accept multiple resource names or patterns such as `"shot_*"`. Use `catalog.bind(Scene, "scene")` when a decorator is inconvenient. Bindings belong to that catalog instance; other unbound resources return plain `Resource` objects.

This example increments the version in memory. Checking existing files, choosing the next available version, and reserving it are host responsibilities.

## 18. Register readers when a tool needs them

Register readers when callers should open a resource without choosing a loader themselves. The definition selects a reader ID from its extension; your host supplies the callable. This example demonstrates dispatch by returning the path:

```python
from namespec import Catalog

catalog = Catalog.from_string("""
spec 1
stem = one of "hello"
ext = one of "txt"
readers { txt = "plain_text" }
resource note {
    name = "{stem}.{ext}"
    location = "notes/{name}"
    reader = readers[ext]
}
""")
catalog.register_reader("plain_text", lambda path: path.as_posix())

note = catalog.parse("hello.txt")
print(note.reader_id)  # plain_text
print(note.read())  # notes/hello.txt
```

For actual text reading, register a callable such as `lambda path: path.read_text(encoding="utf-8")`. It receives a `pathlib.Path`; the file must exist and reader exceptions propagate to your host. No readers are bundled or imported by a rule file.

A relative location is resolved by the host relative to its working directory, not relative to the `.names` file. Prefer declared absolute roots when the host's working directory varies.

## 19. Load one shared convention across tools

Use `load_rules` when multiple modules should share one catalog, class bindings, and reader registry in a Python process:

```python
from namespec import load_rules

catalog = load_rules("STUDIO_NAMES", default="examples/guide.names")
print(catalog.parse("101_120_0040_comp_v003.nk").kind)  # scene
```

The environment variable names a rule file; an unset or blank variable uses the default. Set it in your DCC launcher. For this tutorial, in PowerShell:

```powershell
$env:STUDIO_NAMES = (Resolve-Path examples/guide.names).Path
```

Or in bash/zsh:

```bash
export STUDIO_NAMES="$PWD/examples/guide.names"
```

`load_rules` caches the catalog per process and argument set, including registered classes and readers. If the environment variable or rule file changes during that process, call `load_rules.cache_clear()`, reload, and register your classes/readers on the new instance. Existing references still point at the old catalog. Direct `Catalog.from_file` calls create fresh instances.

In another Python project, install this package as a dependency as well as distributing your `.names` file. For development in a sibling uv project, run `uv add --editable ../namespec` from that project's root. For deployment, use a versioned build and rule file; the [developer guide](../developer.md) covers building and checking the package. A DCC uses its own Python environment, so ensure the package is available to that interpreter.

A practical integration starts small:

1. A save dialog calls `validate` and shows its diagnostics.
2. A publisher parses the scene path and derives output paths from those fields.
3. A browser lists files itself, then parses them with the expected resource kind.
4. A farm task validates its output location before writing.

Definitions are immutable compiled snapshots. Inspect them through `catalog.resources["scene"]`, `catalog.fields["version"]`, or a parsed resource's `definition`. To change a convention, edit its source and compile again. `catalog.definition.to_dict()` gives an independent JSON-compatible representation. The package includes type information for editors and type checkers.

You can also export it:

```console
uv run --locked namespec examples/guide.names export --output rules.json
```

Export is structured data for inspection and downstream tooling. There is currently no JSON importer or alternate-language Namespec runtime included.

## 20. Build your own convention

1. Collect real filenames and complete paths, including a few historical mistakes.
2. Start with one resource. Mark the values that change and choose exact enums, integer rules, or text patterns for them.
3. Keep delimiters outside field patterns wherever possible. Preserve identifiers as text when their exact spelling matters.
4. Write successful examples and specific rejects beside the rules. Include complete derived fields in `expect`.
5. Add locations and roots, then composites, optional groups, or folder resources when a tool needs them.
6. Test changes before distributing the file. Use strict generation and a filesystem policy when your integration needs those guarantees.
7. Keep file discovery, storage access, version allocation, and application behavior in host code.

There are no rule imports, aliases, or project overlays yet. Keep the convention in one explicit file and version it alongside the tools that depend on it.

| Symptom | First thing to check |
| --- | --- |
| `rules.names` cannot be found | Run from the repository root and confirm the file is not named `rules.names.txt` |
| The new rule seems ignored | Save the file, then reload your catalog or clear the `load_rules` cache |
| A path fails but its basename works | Check its root, slashes, and repeated fields; `source="location"` restricts diagnostics to the location template |
| Generation reports missing fields | Inspect `missing_context`; supply those fields to `with_context` or `locate` |
| Changing a composite part conflicts | Use `Resource.replace` so its parent values are recomputed |
| An input matches multiple resources | Pass the expected kind or make the resource patterns more distinct |
| Filesystem policy is unavailable | Run with the `filesystem` extra installed in that same environment |
| A read cannot find its handler or file | Register the reader on this catalog and check the resolved location |

For a larger fictional convention, read [studio.names](../examples/studio.names) and its [CSV test cases](../tests/cases/README.md). Use the [reference](reference.md) for exact grammar, diagnostics, and method signatures; the [editor guide](../editors/vscode/README.md) for live feedback; and the [developer guide](../developer.md) for contributing, tests, and packaging.
