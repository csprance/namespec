# Reference

Use this page to look up a method, rule, or error. Start with [what Namespec is for](../README.md#the-everyday-workflow) if you are deciding how it fits your tool, or the [guide](guide.md) to use an existing convention and then write your own.

## When to select a source

Normally, write `catalog.parse(value)`. It recognizes a filename or a declared path without a hint.

The source options refer to two entries a rule can contain:

```text
resource model {
    name = "{asset}_{lod}_v{version}.{ext}"
    location = "{root}/{job}/assets/{asset}/{lod}/{name}"
}
```

| Source | Meaning | When you would choose it |
| --- | --- | --- |
| `"auto"` (default) | Try both templates | Most tools: accept either a filename or a path |
| `"name"` | Check only the `name =` template | A filename-only save box must not accept a pasted full path |
| `"location"` | Check only the `location =` template | A publish check must verify the root and folders as well as the filename |

With those rules, `Donut_high_v004.abc` is a valid name, but it cannot prove that a file is under the right project folder. Choosing location for a publish check makes that missing information a failure:

```python
from namespec import Catalog

catalog = Catalog.from_file("examples/guide.names")
filename = "Donut_high_v004.abc"
path = "J:/jobs/show17/assets/Donut/high/Donut_high_v004.abc"

print(catalog.validate(filename, "model").valid)  # True: ordinary automatic recognition
print(catalog.validate(path, "model").valid)  # True
print(catalog.validate(path, "model", source="name").valid)  # False: filename box
print(catalog.validate(filename, "model", source="location").valid)  # False: missing layout
print(catalog.validate(path, "model", source="location").valid)  # True: full layout checked
```

This checks text against the declared layout; it does not check whether the file exists. For filesystem operations, parse the valid input and use the resulting `resource.path`.

An explicit source also resolves the unusual case where both templates accept an input but assign different fields. Namespec reports `ambiguous_source` instead of choosing silently; `catalog.inspect(value)` exposes the competing readings.

The three source values are built into Namespec and appear in the method signatures, editor type hints, and `help(catalog.parse)`. Resource kinds such as `"model"` and root labels such as `"windows"` are defined by your catalog: discover them through `catalog.resources` and `catalog.roots`. After parsing, `resource.source` tells you which template matched.

## Terms

| Term | Meaning |
| --- | --- |
| Field | A reusable rule for one value, such as `asset`, `version` or `ext`. |
| Composite | A field described by a template of other fields, such as `Shot = "{Sequence}_{shotnum}"`. |
| Template | Literal text with `{field}` placeholders and optional `[…]` groups. |
| Resource definition | A named convention with a filename template, a location template, or both. |
| Catalog | The compiled fields, resources, examples and settings from one rule document. |
| `Resource` | A successfully parsed instance, with a resource kind and typed field values. |
| Source | Which template to use: `"name"` for a filename, `"location"` for a path, or the default `"auto"` to consider both. |
| Metadata | A resource definition's static `meta` data. It is separate from the values extracted from a name. |

## Rule documents

A document is UTF-8 text starting with `spec 1`. Declarations may follow in any order, so a template can refer to a field declared later. At least one resource is required. Whitespace separates tokens; semicolons are not used. `//` starts a comment outside a string.

Identifiers use ASCII letters, digits and underscores, beginning with a letter or underscore. Names are case-sensitive. Fields cannot be named `name`, `root`, `meta`, `spec`, `resource`, `example`, `reject`, `readers`, `roots` or `normalize`.

Strings use single or double quotes and cannot contain literal line breaks. `\"`, `\'` and `\\` escape quote characters and backslashes. Other backslashes are preserved: `"\d+"` contains the regex `\d+`, and `"\n"` contains a backslash followed by `n`, not a newline.

| Declaration | Syntax |
| --- | --- |
| Text field | `asset = text matching "[A-Za-z]+" examples "Donut", "Chair"` |
| Choice field | `ext = one of "abc", "usd"` |
| Integer field | `version = integer minimum 1 maximum 999 padded to 3 digits` |
| Composite field | `Shot = "{Sequence}_{shotnum}"` |
| Resource | `resource model { name = "{asset}.{ext}" location = "/assets/{name}" }` |
| Roots | `roots { linux = "/mnt/jobs" windows = "J:/jobs" }` |
| Normalization | `normalize { slashes = "forward" drive = "upper" }` |
| Reader mappings | `readers { abc = "alembic" usd = "usd" }` |
| Passing example | `example model { input = "Donut.abc" expect { asset = "Donut" ext = "abc" } }` |
| Rejection | `reject model { input = "Donut.exe" expect = "invalid_field" }` |

### Fields and values

Text rules use Python's `re` syntax and must not match an empty string. Their optional `examples` are a comma-separated list of strings; each must match the rule. Namespec uses them for sampling rather than trying to generate text from a regex.

Choices are nonempty, distinct strings. Their declared order participates in matching when more than one choice fits a boundary.

An integer's `minimum` is required. `maximum` and `padded to N digits` are optional, in that order. The maximum is inclusive and must be at least the minimum. Padding defaults to zero and must be nonnegative. It is a minimum digit count excluding the sign: `-1` padded to four digits is `-0001`. Values larger than the padding width retain all their digits. A negative minimum permits a minus sign. Leading plus signs, negative zero and spellings with incorrect padding are rejected.

Parsing returns Python `int` values for integer fields and strings for other fields. Formatting an integer requires a Python `int`; strings, floats and booleans are not accepted as integers. `/`, `\`, carriage returns and line feeds are forbidden inside field values, even if a text regex or choice would otherwise allow them.

### Resources and templates

A resource needs `name`, `location`, or both. A resource with only a location describes a folder. Automatic parsing includes folders; explicit `source="name"` inspection excludes them. A resource with only a name can be parsed and formatted but cannot be located or read.

- `{field}` inserts a declared field. Every template must contain at least one declared field; a completely literal name or a location containing only `{root}` is unsupported.
- Fields need literal non-alphanumeric separators between them, such as `_`, `.`, `/` or a space. Formatting expressions such as `{version:03}` and conversions such as `{asset!r}` are unsupported; put formatting rules on the field.
- `{name}` is available only in a file resource's location. It inserts the complete filename template. A file location must include every leaf field from its filename, whether through `{name}` or explicit placeholders.
- `{root}` is available only at the start of a location, once, outside optional groups. Roots must be declared before the catalog can compile, though their declaration may appear anywhere in the document.
- `[…]` makes a whole group optional. It must contain a field, start or end with a literal separator, and cannot nest, including through composite expansion.
- An absent optional field is omitted from parsed fields. During formatting, omitting its value or supplying `None` omits the group. Supplying any member makes all members of that group required. Repeated groups must agree on presence.
- Composites expand to their leaf fields. Parsing reports their assembled strings alongside their parts. Formatting accepts a composite string, its parts, or both when they agree. Composite cycles are rejected.
- `{{` and `}}` spell literal braces; `[[` and `]]` spell literal brackets. For example, `"[[{asset}]]"` produces `[Donut]`, while `"{{name}}/{name}"` retains a literal `{name}` before the generated filename.

Repeated fields must have the same value wherever they occur. A mismatch between folder and filename is reported against the conflicting leaf field, including when it belongs to a composite.

### Roots and normalization

Roots map names to literal prefixes. A prefix must be nonempty, use forward slashes, contain no braces, and have no trailing slash. Duplicate prefixes are rejected. Generation accepts either a declared root name or its prefix. A parsed resource exposes the prefix string as `resource["root"]`, the prefix as a `Path` through `resource.root`, and its label through `resource.root_name`. The properties return `None` when no root was parsed.

The only normalization options are `slashes = "forward"` and `drive = "upper"` or `"lower"`. Either option may be omitted. They apply to location inputs, root declarations and literal location text, so generated locations use the same spelling the parser expects. Prefixes that become identical after normalization are rejected.

Normalization does not change filenames, resolve `.` or `..`, remove repeated separators, or change the case of folders and files. Drive-case conversion applies only to ASCII letters. Both options preserve string length, so diagnostic offsets still refer to the supplied string.

### Metadata and readers

A resource may contain `meta { key = value ... }`. Values are strings, integers, or flat lists of strings and integers, including empty or mixed lists. Metadata does not affect matching. Python exposes lists as tuples; JSON export uses arrays.

`reader = readers[ext]` selects a handler ID using an enum field present in the filename template. Every choice of that enum must have a global `readers` mapping. Handler IDs are nonempty strings. The rules do not import or execute handlers; application code registers them with `catalog.register_reader(...)`. An optional selector is allowed, but an instance without it has no reader.

### Examples and rejections

Use `input =` for filename examples and `location =` for location examples. Each example names the resource it checks, so it does not test whether that input is ambiguous across several resources.

A passing example's `expect` block must list exactly the parsed fields, including composites and the root prefix when present. Values and types must agree: an integer expectation is `version = 4`, not `version = "4"`. Omit absent optional fields. Static `meta` data is not part of these expectations.

A rejection passes when its expected code appears among the validation diagnostics. It does not require that code to be the only diagnostic. Loading a catalog checks declarations and references but does not run examples; call `run_examples()`, `check_examples()`, or the CLI `test` command.

## Matching and generation policies

Matching consumes the whole input and has two readings:

1. The precise reading requires every field's rule to match its entire value. Fields may contain template punctuation when their rules allow it. Composable patterns retain their regex selection order, including lazy quantifiers and enum preference. Context-sensitive patterns, including anchors, lookarounds, backreferences, named groups and global flags, are matched against isolated field values, trying their longest valid boundary first. Other fields retain their own selection order. Separator-free field readings take precedence over invalid captures containing path separators.
2. If precise matching fails, the diagnostic reading also allows punctuation-free chunks that violate their field rule. It reports the wrong fields with offsets and retains correctly parsed fields. If a bad value crosses punctuation, its pieces may not line up and the result can be `pattern_mismatch`.

Named captures and backreferences belong to each field, including repeated occurrences. Regexes come from the rule author; they are not sandboxed and have no runtime timeout. Prefer bounded patterns for potentially long inputs. Regex syntax depends on the Python version running Namespec.

### Strict generation

Catalog construction and loading accept `strict=False`. With `strict=True`, `format`, `locate` and `samples` verify that generated text parses back to the supplied logical values. A changed value raises `non_roundtripping_value`.

Strict generation does not detect every possible interpretation of an input and does not change ordinary parsing. It also does not require a generated name to identify only one resource: generation checks the selected resource's template. Use nonoverlapping field rules and resource conventions when unique interpretation is required. `Resource.replace`, `with_context`, and `related` always perform this roundtrip check, regardless of the catalog setting.

### Filesystem policies

`filesystem=None` is the default and adds no platform filename checks. To select a policy, install the optional `namespec[filesystem]` extra and pass `filesystem="posix"`, `"windows"` or `"portable"` when loading the catalog. The extra uses `pathvalidate` for component validation.

| Policy | Behavior |
| --- | --- |
| `posix` | POSIX filename rules; `/` separates location components. |
| `windows` | Windows filename rules, including reserved names, invalid characters and trailing spaces or dots; `/` and `\` separate location components. |
| `portable` | Universal filename rules suitable for Windows and POSIX; separator handling follows the Windows policy. |

All policies reject `.` and `..` components and ASCII control characters, and use a 255-byte UTF-8 component limit. A Windows drive prefix is handled separately from filename components. Policies apply to complete names and locations during validation, inspection, parsing and generation. They do not apply to standalone `validate_field` or `format_field` calls because a field may be only part of a filename.

These are spelling checks, not filesystem existence, permissions, symlink containment or total-path-length checks. `pathlib` may normalize an input before Namespec receives it; pass the original string when that distinction matters. An unknown policy raises `ValueError`; selecting a policy without the extra raises `NameSpecError` with `unavailable_filesystem_policy`.

## Python API

Import public objects from `namespec`. The signatures below omit type annotations. `/` means the preceding arguments are positional-only; `*` means following named arguments are keyword-only.

### Loading and caching

```text
Catalog.from_string(source, *, strict=False, filesystem=None)
Catalog.from_file(path, *, strict=False, filesystem=None)
Catalog.from_env(variable="NAMESPEC_RULES", default=None, *, strict=False, filesystem=None)
load_rules(variable="NAMESPEC_RULES", default=None, *, strict=False, filesystem=None)
Catalog(definition, *, strict=False, filesystem=None)
```

`from_string` and `from_file` create a new catalog each time. `from_file` reads UTF-8 text and accepts string paths or path objects. The advanced constructor accepts a `Definition` from `namespec.models`, not a JSON dictionary.

`load_rules` reads the path named by the environment variable. An unset or whitespace-only variable falls back to `default`. With neither, it raises `missing_rules`. It caches by variable name, default argument and policy options. Equivalent calls to `load_rules` and `Catalog.from_env` share the same catalog, class bindings and registered readers. Direct construction, `from_file` and `from_string` do not participate in this cache.

File edits and environment changes do not invalidate cached catalogs automatically. `load_rules.cache_clear()` clears the cache for subsequent loads; objects already held by callers remain usable and unchanged. `load_rules.cache_info()` reports cache statistics. A different default or policy option gives a separate cache entry, even when it selects the same file.

Definition mappings and nested metadata are immutable snapshots. `catalog.fields` maps field names to their definitions, and `catalog.resources` maps resource names to their definitions. A parsed resource's `definition` is the same immutable definition exposed in `catalog.resources`. `catalog.definition.to_dict()` returns independent JSON-compatible dictionaries and lists, omits source spans, and includes normalized root prefixes and location text. There is no JSON-import constructor. The distribution includes a `py.typed` marker for type checkers.

### Parsing and validation

```text
catalog.parse(text, resource=None, *, source="auto")
catalog.validate(text, resource, *, source="auto")
catalog.inspect(text, *, source="auto")
catalog.validate_field(name, text)
```

`parse` returns a `Resource` or a bound subclass. The default `source="auto"` tests both available templates, including folder locations. It does not guess from separators or check the filesystem. Pass `source="name"` or `source="location"` to restrict matching explicitly.

With a resource name, `parse` validates that resource and raises its diagnostics on failure. Without one, it requires exactly one distinct valid reading: several resource kinds raise `ambiguous_resource`, none raise `no_match`. Different name and location readings for the same kind raise `ambiguous_source`; select a source to disambiguate. If both templates return identical fields for the same kind, they count as one reading and the location source wins. Use `inspect` to investigate candidates after `no_match`.

`validate` returns a `Validation` for one resource. An invalid input is a result, while an invalid operation, such as an unknown resource or source, still raises. Automatic validation returns the matching source, or the single useful diagnostic candidate. If both invalid templates provide useful diagnostics, their messages identify the source and only fields on which they agree are retained. `inspect` checks all resources that have the requested source and returns an `Inspection`.

`validate_field` checks one field's spelling without a surrounding template and uses `source="field"` in its result. Integer inputs must be strings such as `"004"`; use `format_field` for logical integers. A simple field returns its own key; a composite returns its parts and nested composites, without an additional key for the outer composite itself.

Text-input methods accept strings and string-valued path objects. A `pathlib.PurePath` is converted with `as_posix()` before any configured normalization.

| Result | Attributes |
| --- | --- |
| `Validation` | `resource`, `input`, `fields`, `diagnostics`, `source`, `valid`; `to_dict()` includes these and the computed `valid` flag. `source` identifies the matched template, or is `"auto"` when a failed result combines templates. Location results contain normalized input. Invalid results may retain valid fields. |
| `Inspection` | `status` is `"valid"`, `"ambiguous"` or `"invalid"`; `matches` contains valid `Validation` objects; `candidates` contains invalid results with field-level diagnostics, excluding structural `pattern_mismatch` results. `to_dict()` exports them. |
| `Diagnostic` | `code`, `message`, and optional `field`, `expected`, `actual`, `span`, `composite`. |

### Formatting and locations

```text
catalog.format(resource, base=None, /, **overrides)
catalog.locate(resource, base=None, /, **overrides)
catalog.format_field(name, value)
catalog.normalize(text, source="location")
catalog.root_name(value)
catalog.roots
```

`format` returns a filename string; `locate` returns a native `pathlib.Path`. Neither touches the filesystem. Pass the resource name and optional base mapping positionally. A parsed resource itself is a mapping, so it can be the base. Keyword arguments are field values, and override matching keys in that mapping. Unused keys are ignored so fields from one resource can help build another.

```python
catalog.format("scene", scene, version=4)
catalog.locate("render", scene, root="mac", job="show17", frame="####", image_ext="exr")
```

The `base` mapping is not passed as `base=...`: because the parameter is positional-only, that keyword would be treated as a field named `base`. Conflicting composite and part values still raise even when one arrived through an override. Use `scene.replace(shotnum="0041")` to update an existing instance and recompute its derived composites.

Paths use the host's [standard `pathlib` behavior](https://docs.python.org/3/library/pathlib.html) and separators. `.as_posix()` gives forward-slash display; `str(path)` or `os.fspath(path)` gives the native string form. Namespec validates generated template text before constructing the path. Creating a `Path` does not translate a foreign drive or mount into a usable local mount, and `pathlib` can normalize spelling such as `.` components.

`format_field` validates and spells a single logical value, including integer padding. For a composite, pass its complete string. `normalize` only transforms locations, with `source="location"` as its default. `roots` returns a copy of the declared root-name-to-prefix mapping; `root_name` accepts a root name or its normalized prefix.

### Sampling and inline tests

```text
catalog.samples(resource, *, limit=10, **overrides)
catalog.run_examples()
catalog.check_examples()
```

`samples` is an iterator of at most `limit` generated filenames. It uses enum choices, integer minimum and minimum plus one within any maximum, and authored text examples. Composite values may be supplied through overrides; otherwise their parts supply the samples. Optional groups are sampled wholly absent or present, and repeated groups agree on presence. A group without enough authored examples can remain absent; explicitly requesting its presence requires samples or values for its remaining fields.

Missing samples for required values raise `missing_sample`. A zero limit produces no names; a negative limit raises `ValueError`. Folder resources have no filename samples. `limit` is the sampling option, so this method cannot use that keyword to override a field also named `limit`; format that value directly instead. Sampling is bounded example generation, not exhaustive enumeration or proof that resource conventions do not overlap.

`run_examples` returns an `ExampleResult` for every authored example and rejection. Each has `example`, its block `span`, `failures`, and a computed `passed` flag. `check_examples` returns the flattened failure diagnostics; an empty list means all authored examples passed. Neither method invents tests when the document contains none.

### Parsed resources

| Member | Behavior |
| --- | --- |
| `resource.catalog` | The catalog that created the instance. |
| `resource.kind` | Its resource definition's name. |
| `resource.source` | The matched template, `"name"` or `"location"`. |
| `resource.definition` | The immutable definition for this kind, also in `catalog.resources`. |
| `resource["version"]`, `.get(...)`, `.keys()`, `.items()` | Read-only mapping access to typed fields. Missing keys raise `KeyError`; `get` accepts a default. Iteration yields field names and `dict(resource)` makes a copy. |
| `resource.fields` | A copy of the parsed field values, including available composites. |
| `resource.metadata` | A copy of its definition's static metadata; nested values remain immutable. |
| `resource.name` | Its formatted filename; raises `missing_name` for a folder. |
| `resource.path` | A native `Path` computed from the parsed source. A parsed filename remains a basename path; a parsed location has its full declared path. No filesystem access occurs. |
| `Path(resource)`, `os.fspath(resource)` | The same path through Python's path protocol, for APIs accepting path-like objects. |
| `resource.root`, `resource.root_name` | The parsed root prefix as a `Path` and its declared label, or `None` when no root was parsed. |
| `resource.missing_context` | A tuple of missing required location fields in template order. Optional groups contribute fields only once one member is present. A definition without a location returns `()`. |
| `resource.locate(**context)` | Returns a location `Path`, supplying missing context without changing this resource. A context value that disagrees with a parsed value or its Python type raises `context_conflict`. |
| `resource.with_context(**context)` | Returns a validated location resource of the same class. Requires all missing context, rejects unknown location fields and conflicts, and leaves the original unchanged. |
| `resource.replace(**changes)` | Returns a validated instance of the same class with updated fields, retaining its source and location context and keeping the original unchanged. |
| `resource.related(kind, /, **overrides)` | Reuses these fields with explicit overrides to derive a validated resource of another kind. Uses the target location if defined, otherwise its filename, and returns the target's bound class. |
| `resource.reader_id` | The selected handler ID; raises `missing_reader` if no selector exists or its optional field is absent. |
| `resource.read(**context)` | Resolves a location and calls its registered reader with a host `pathlib.Path`; returns the handler's result. |

`replace` accepts fields belonging to the source originally parsed. Updating a part recomputes its composites; updating a whole composite replaces its parts. Setting an optional value to `None` removes it, and setting a whole optional composite to `None` removes its parts. Explicit whole/part disagreements still raise, including removing a composite while supplying one of its parts. Replacements always undergo strict generation and the catalog's filesystem policy.

Use `with_context(**context)` to turn a parsed basename into a resource at its declared location. This requires complete context and changes the returned resource's source to `"location"`; subsequent replacements preserve those location fields. `locate(**context)` returns only the path. Neither method overwrites parsed values. `related` accepts deliberate overrides for its target, ignores fields the target does not use, and requires enough values for its selected template. These operations neither find files nor call readers.

`related` validates composite and part overrides just like `catalog.format`; it does not silently discard inherited composite values. To change a composite's part before deriving another resource, use `scene.replace(shotnum="0041").related("render", frame="####", image_ext="exr")`. This recomputes the source composites before passing them to the target.

### Resource classes and reader handlers

```text
catalog.resource(*kinds)         # Decorator for a Resource subclass.
catalog.bind(cls, *kinds)        # Equivalent explicit binding.
catalog.resource_class(kind)    # Bound class, or Resource.
catalog.register_reader(name, reader)
```

Bindings accept exact resource names or case-sensitive shell patterns such as `"shot_*"`, using `fnmatch` syntax. At least one name or pattern is required. An unknown exact name raises; an unmatched pattern binds nothing. Rebinding the same class is allowed, while binding a different class to an already bound kind raises `duplicate_binding` before making partial changes.

Subclass `Resource` to add behavior and keep its initializer unchanged. Parsing constructs the registered class with the catalog, resource kind and parsed fields. Bindings belong to the catalog instance and do not affect resources already created.

`register_reader(name, reader)` associates a handler ID with a callable, replacing any prior handler under that ID. It does not call the handler. `Resource.read` raises `unavailable_reader` if the selected ID is unregistered, and propagates exceptions raised by a registered handler. It needs a location template and enough context to build a path. Namespec supplies no built-in readers and does not read the described resource until application code explicitly calls a reader.

## Diagnostics and errors

`NameSpecError` is a `ValueError` subclass with a `diagnostics` list. Definition and operation failures raise it; ordinary validation failures are carried by `Validation.diagnostics`. Python argument misuse can raise `TypeError` or `ValueError`, and file-loading errors such as `FileNotFoundError` propagate from the Python API.

A diagnostic `span`, when available, is a half-open pair of character offsets `(start, end)`. For input validation it refers to the name or location string, not bytes. For a definition error or `example_failed`, it refers to the rule text. Located definition exceptions include a one-based line and column in their message. General errors such as a missing resource declaration may have no span.

An `example_failed` points at a mismatched expectation, the `expect` block when fields are missing, or the input when validation itself failed. `composite` identifies the owning composite when a leaf-level error has that context.

### Definition errors

| Code | Meaning |
| --- | --- |
| `syntax_error` | The document does not parse. |
| `unsupported_spec` | The `spec` number is not 1. |
| `reserved_field` | A field uses a reserved name or keyword. |
| `invalid_pattern`, `empty_field`, `invalid_sample`, `invalid_integer`, `duplicate_choice` | A field rule is unusable. |
| `duplicate_definition` | A field, resource, reader, root, resource entry, metadata key or expected field is repeated. |
| `invalid_resource` | A resource has neither name nor location. |
| `invalid_root`, `duplicate_root`, `missing_root` | A prefix is invalid or repeated, or `{root}` has no declarations. |
| `invalid_normalize` | An unknown normalization option or value. |
| `empty_handler` | A reader mapping has an empty handler ID. |
| `missing_resource` | No resources were declared. |
| `unknown_resource`, `unknown_field` | A reference names something undeclared. |
| `invalid_template`, `ambiguous_template`, `cyclic_field` | A template cannot compile, lacks required separators, or has cyclic composites. |
| `incomplete_location` | A file location omits a leaf field from its filename. |
| `invalid_reader`, `missing_reader_mapping` | A reader selector is invalid or an enum choice lacks a mapping. |
| `missing_location`, `missing_name` | An example targets a source the resource does not have. |

### Input and generation diagnostics

| Code | Meaning |
| --- | --- |
| `pattern_mismatch` | The input does not fit the template structure; no fields are assigned. |
| `missing_field` | A required value is absent or empty. |
| `invalid_field` | A value breaks its field rule, bounds, choices or root declaration. |
| `noncanonical_field` | An integer has the wrong spelling or padding; `expected` gives the canonical spelling. |
| `invalid_integer` | An integer exceeds a runtime conversion limit. |
| `invalid_type` | Generation received the wrong Python type. |
| `conflicting_field` | Repeated values or presence disagree, or supplied composites and parts conflict. |
| `reserved_separator` | A field value contains a path separator, carriage return or line feed. |
| `example_failed` | An inline example or rejection did not hold. |
| `non_roundtripping_value` | Strict generation, `replace`, `with_context`, or `related` would lose or change supplied field values. |
| `unsafe_path` | A selected filesystem policy rejects the name or a path component. |

### Operation errors

| Code | Meaning |
| --- | --- |
| `ambiguous_resource`, `no_match` | Parsing without a selected resource found several valid matches or none. |
| `ambiguous_source` | A resource's filename and location templates give different valid readings; select a source explicitly. |
| `unknown_resource`, `unknown_field` | An operation names an unknown resource or field. |
| `invalid_source` | A parsing operation's source is not `auto`, `name`, or `location`. |
| `missing_location`, `missing_name` | The resource lacks the requested template. |
| `missing_sample` | Sampling needs an authored example or explicit value. |
| `context_conflict` | `Resource.locate` or `with_context` context disagrees with a parsed value. |
| `missing_reader`, `unavailable_reader` | Reader selection is absent, or its handler is unregistered. |
| `duplicate_binding` | A resource is already bound to a different class. |
| `unknown_root` | `root_name` received an undeclared name or prefix. |
| `missing_rules` | The environment loader found neither a configured path nor a default. |
| `unavailable_filesystem_policy` | A filesystem policy was selected without its optional dependency. |

## Command line

```text
namespec <rules> [--strict] [--filesystem posix|windows|portable] <command>

namespec <rules> inspect <text> [--resource R] [--source auto|name|location]
namespec <rules> test [--json]
namespec <rules> export [--output file.json]
namespec <rules> format <resource> '<json fields>'
namespec <rules> locate <resource> '<json fields>'
```

`<rules>` is a file path, or `-` to read UTF-8 rule text from stdin. Place catalog options `--strict` and `--filesystem` before the command. JSON fields must be an object; quote it according to your shell. For example, from the repository root:

```sh
uv run namespec examples/guide.names --strict format model '{"asset":"Donut","lod":"high","version":4,"ext":"abc"}'
```

`export --output` also accepts `-o`.

`inspect` without a resource prints an inspection; with `--resource`, it prints that resource's validation. Its source defaults to `auto`, considering both names and locations. `format` and `locate` print an object containing the generated string; CLI locations retain forward slashes on every platform. Export prints the JSON model or writes it to the requested path and prints a receipt.

Output is JSON except for plain `test`, which prints a `file:line:column:` line per failure and a count. `test --json` reports every example, its source, input, span, line, column and failures. Located definition errors in JSON include line and column. Invalid CLI arguments use the usual argparse usage message.

| Exit code | Meaning |
| --- | --- |
| `0` | Success, including a test document with no examples. |
| `1` | Invalid or ambiguous inspected input, or failed examples. |
| `2` | Definition, operation, file I/O, JSON or command-line usage error. |

## Scope and further references

Namespec does not implement imports or overlays between rule files, aliases, filesystem searching, fuzzy name recovery or bundled readers. The JSON model describes the rules; it is not a cross-language runtime and does not guarantee another regex engine will interpret them identically.

- [Guide](guide.md): learn the language and build a working integration.
- [Editable conformance tables](../tests/cases/README.md): row-by-row expectations for the supplied conventions.
- [VS Code extension](../editors/vscode/README.md): editing, navigation and live example checks.
- [Development](../developer.md): contributor setup, tests and packaging.
