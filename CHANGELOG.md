# Changelog

All notable changes to Namespec are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- A rule language for names, metadata and resource locations, written in `.names` files and read by a small hand-written parser with no third-party dependencies. Rules declare typed fields (text patterns, enums, padded integers and composite fields built from other fields), resource name and location templates with optional `[...]` groups, folder resources, declared roots, a `normalize` block for pasted Windows paths, `meta` blocks, reader mappings, and `example` and `reject` cases that run as tests. `examples/guide.names` walks through every construct; `examples/assets.names` and `examples/studio.names` come with CSV tables of expected results.
- `namespec.Catalog` parses, validates, formats and locates names (`parse()`, `validate()`, `inspect()`, `format()`, `locate()`, `validate_field()`, `format_field()`, `samples()` and `check_examples()`). Matching reads a name precisely first and falls back only to explain a failure, so errors name the field that is wrong and keep the fields that were right. `format()` and `locate()` take a base mapping plus overrides. Text arguments accept `pathlib` objects.
- `Catalog.resource()` binds `Resource` subclasses to resource kinds, so parsed paths come back carrying the methods a studio writes for them. `register_reader()` and `Resource.read()` pass a located path to a reader the host application supplies.
- `load_rules()` and `Catalog.from_env()` load the rule file an environment variable names, once per process.
- The `namespec` command-line tool runs `inspect`, `test`, `export`, `format` and `locate` against a rule file, or against rule text on stdin when the path is `-`. `test` prints one `file:line:column:` line per failed example and a count, or every result as JSON with `--json`; the other commands write JSON.
- Failing examples say what differed and where: a wrong `expect` value points at that entry, fields left out of `expect` are listed ready to paste, and a name that does not parse or a rejection that is accepted points at the `input`. `Catalog.run_examples()` returns a result for every example. Definition errors, including bad field samples and unknown template fields, point at the declaration at fault and report its line and column.
- A local VS Code extension in `editors/vscode` for `.names` files: syntax highlighting, hover previews of declarations, and Go to Definition (Ctrl+click or F12) and Peek Definition for fields, composite parts, resources, roots and reader mappings. With the Python package installed, it runs a file's examples as you type and underlines failures where they happen, and lists every example in the Testing view with a run button in the gutter.
- MIT license.
