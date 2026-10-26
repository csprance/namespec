# Reference

The README teaches the language. This page lists it.

## The file

A rule document starts with `spec 1` and then holds declarations in any order. `//` starts a comment. Strings use double or single quotes; `\"`, `\'` and `\\` are escapes and every other backslash is kept, so `"\d+"` is the regex `\d+`.

| declaration | syntax |
| --- | --- |
| text field | `name = text matching "regex" examples "a", "b"` (examples optional) |
| choice field | `name = one of "a", "b"` |
| integer field | `name = integer minimum N padded to N digits` (padding optional) |
| composite field | `name = "{part}_{part}"` |
| resource | `resource name { name = "…" location = "…" reader = readers[field] meta { … } }` |
| roots | `roots { key = "/prefix" … }` |
| normalize | `normalize { slashes = "forward" drive = "upper" }` |
| readers | `readers { choice = "handler" … }` |
| example | `example resource { input = "…" expect { field = value … } }` |
| rejection | `reject resource { input = "…" expect = "code" }` |

`location =` may replace `input =` in examples and rejections. A resource needs a `name`, a `location`, or both; `location` only makes a folder resource. `meta` values are strings, integers, or `[lists]` of either. Field names cannot be `name`, `root`, or a block keyword.

## Templates

- `{field}` is a blank. The text between blanks is literal. Two blanks must be separated by punctuation.
- `{name}` in a location is the resource's filename template.
- `{root}` must start a location and matches any declared root as a literal prefix.
- `[…]` is an optional group. It needs at least one field, must start or end with punctuation, and does not nest. Absent fields are omitted from the result. A group present in one occurrence and absent in another is a conflict.
- A composite field expands to its parts before matching and is reported alongside them.
- `{{` and `}}` are literal braces.

## Matching

1. The precise reading: each field's own rule is placed in its blank, exactly as one regular expression built from the rules would read the name. A value may contain the template's punctuation when its rule allows it; the leftmost reading wins. A correct name needs only this reading.
2. If that fails, the diagnostic reading: each blank takes its rule or, failing that, any punctuation-free chunk. The wrong pieces are then reported by field, with offsets, and the good pieces are returned. When a wrong value sits in a field whose rule crosses punctuation, the pieces may not line up and the result is `pattern_mismatch`.

Both readings run against the whole input. Nothing is altered except what a `normalize` block asks for, and that only for locations. `/`, `\` and newlines are never allowed inside a value.

## Error codes

Definition errors raise `NameSpecError` while loading. Each diagnostic's `span` covers the declaration at fault (the token, the sample, the template entry), and the exception's message starts with that line and column.

| code | meaning |
| --- | --- |
| `syntax_error` | the file does not parse |
| `unsupported_spec` | the `spec` number is not 1 |
| `reserved_field` | a field named `name`, `root` or a keyword |
| `invalid_pattern`, `empty_field`, `invalid_sample`, `invalid_integer`, `duplicate_choice` | a field rule is unusable |
| `duplicate_definition` | a field, resource, reader, root, meta key or expected field twice |
| `invalid_resource` | a resource with neither name nor location |
| `invalid_root`, `duplicate_root`, `missing_root` | roots: bad prefix, repeated prefix, `{root}` without roots |
| `invalid_normalize` | unknown normalize option or value |
| `empty_handler` | a reader with an empty handler id |
| `missing_resource` | no resources at all |
| `unknown_resource`, `unknown_field` | a reference to something not declared |
| `invalid_template`, `ambiguous_template`, `cyclic_field` | a template cannot be compiled |
| `incomplete_location` | a location is missing one of the name's fields |
| `invalid_reader`, `missing_reader_mapping` | reader selection on a non-enum field, or a choice without a handler |
| `missing_location`, `missing_name` | an example aimed at the wrong side of a resource |

Validation results carry diagnostics instead of raising.

| code | meaning |
| --- | --- |
| `pattern_mismatch` | the structure does not fit; no fields assigned |
| `missing_field` | a blank is present but empty |
| `invalid_field` | a value breaks its rule; `expected` holds the rule or choices |
| `noncanonical_field` | an integer with the wrong padding; `expected` holds the spelling |
| `invalid_type` | formatting was given the wrong Python type |
| `conflicting_field` | repeated occurrences disagree, or one is present and one absent; `composite` names the owning composite |
| `reserved_separator` | formatting a value that contains a path separator |
| `example_failed` | an inline example or rejection did not hold; the message says what differed |

A span is a pair of character offsets. In a validation it is into the name; in a definition error or an `example_failed` it is into the rule text. An `example_failed` points at the `expect` entry that differed, at `expect { … }` when fields are missing from it, and otherwise at the `input`.

Operations raise with these codes.

| code | meaning |
| --- | --- |
| `ambiguous_resource`, `no_match` | `parse` without a resource found several or none |
| `invalid_source` | source is not `name` or `location` |
| `missing_sample` | `samples` has nothing to generate for a field |
| `context_conflict` | `Resource.locate` context disagrees with a parsed field |
| `missing_reader`, `unavailable_reader` | `read` with no reader field, or no handler registered |
| `duplicate_binding` | a resource bound to two different classes |
| `unknown_root` | `root_name` of an undeclared root |
| `missing_rules` | `load_rules` found neither the variable nor a default |

## Python API

| call | returns |
| --- | --- |
| `Catalog.from_file(path)`, `Catalog.from_string(text)` | a catalog |
| `load_rules(variable="NAMESPEC_RULES", default=None)` | a memoized catalog; `Catalog.from_env` is the same |
| `catalog.parse(text, resource=None, source="name")` | a `Resource` (or bound subclass); raises on failure |
| `catalog.validate(text, resource, source="name")` | a `Validation`: `valid`, `fields`, `diagnostics`, `input` |
| `catalog.inspect(text, source="name")` | an `Inspection`: `status`, `matches`, `candidates` |
| `catalog.format(resource, base=None, **overrides)` | a name |
| `catalog.locate(resource, base=None, **overrides)` | a location |
| `catalog.validate_field(name, text)`, `catalog.format_field(name, value)` | one field alone |
| `catalog.samples(resource, limit=10, **overrides)` | generated names |
| `catalog.run_examples()` | an `ExampleResult` per example: `example`, `span` of its block, `passed`, `failures` |
| `catalog.check_examples()` | the failures alone, as diagnostics; empty when every example holds |
| `catalog.normalize(text, source="location")` | the text after the normalize block |
| `catalog.roots`, `catalog.root_name(value)` | declared roots |
| `catalog.resource(*kinds)`, `catalog.bind(cls, *kinds)`, `catalog.resource_class(kind)` | class binding |
| `catalog.register_reader(id, handler)` | reader handlers |
| `catalog.definition.to_dict()` | the JSON export |

A `Resource` has `kind`, `fields`, `metadata`, `name`, `locate(**context)`, `reader_id` and `read(**context)`. Text arguments accept `pathlib` objects.

## Command line

```text
namespec <rules> inspect <text> [--resource R] [--source name|location]
namespec <rules> test [--json]
namespec <rules> export [--output file.json]
namespec <rules> format <resource> '<json fields>'
namespec <rules> locate <resource> '<json fields>'
```

`<rules>` is a path, or `-` to read the rule text from stdin. Output is JSON, except `test`, which prints a `file:line:column:` line per failure and then a count; `test --json` reports every example with its span, line, column and failures. Definition errors in JSON output carry `line` and `column` beside the span. Exit codes: 0 success, 1 invalid or ambiguous input or failed examples, 2 definition or operation error.

## Not implemented

Imports between files, aliases, filesystem searching, fuzzy recovery, bundled readers. Regex patterns use Python's `re` syntax, so the JSON export describes the rules but does not guarantee another engine reads them identically.

## Tables

[tests/cases](../tests/cases/README.md) explains the CSV tables that hold row-by-row expectations for the shipped conventions.
