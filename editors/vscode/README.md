# Namespec for VS Code

Syntax highlighting for `.names` files: resource declarations, field definitions, keywords, numbers, quoted strings, template placeholders, and `//` comments. Uses your current editor theme, with bracket matching, quote completion, indentation, and the Toggle Line Comment command.

Hover over a reference or declaration to see its complete rule/value in a syntax-highlighted Namespec code block. This uses VS Code's standard hover popup. Hold Ctrl while hovering for VS Code's definition preview, or use **Peek Definition** (Alt+F12 on Windows) to inspect the declaration in an inline editor without leaving your place. Escape closes Peek.

Ctrl+click a reference (Cmd+click on macOS), press F12, or use **Go to Definition** to jump within the current file:

- `{field}` in a name or location template jumps to its field rule, including composite fields such as `Shot = "{Sequence}_{shotnum}"` and fields inside optional `[...]` groups.
- `{part}` inside a composite field's template jumps to the part's rule.
- `{name}` in a location jumps to that resource's `name` assignment.
- `{root}` in a location jumps to the `roots` block.
- Resource names after `example` or `reject` jump to the resource declaration. The hover shows the whole block, including its `meta` entries.
- Expected field names in `expect { ... }` jump to their field rules.
- `readers` in `reader = readers[filetype]` jumps to the mapping block; `filetype` jumps to its field rule.

Definitions can appear before or after references, and navigation and hover follow unsaved edits. The shared index is prepared when a file opens and refreshed shortly after edits, so hover and navigation normally use cached results. Comments, ordinary strings, and escaped template braces do not create links. Undefined references have no target; duplicate declarations offer multiple targets. Navigation uses small JavaScript providers and the same TextMate tokenizer as highlighting, with no Python runtime requirement. Semantic completion is not provided.

## Examples run as you type

The extension runs a file's `example` and `reject` blocks through the Namespec Python package, which is the same check as `namespec rules.names test`. A moment after you stop typing, failures are underlined where they happen and listed in Problems:

- A wrong value in `expect` underlines that field: `Expected lod = "mid", got "high".`
- A name that does not parse, or a `reject` whose name is accepted, underlines the `input`.
- A field the name has that `expect` leaves out underlines the `expect { ... }` block and lists what to add.
- A broken rule, such as a sample that fails its own pattern, an unknown `{field}` or a syntax error, underlines the declaration.

Every example is also a test in the Testing view, with a run button in the gutter beside it. Run one example, a file, or every `.names` file in the workspace; results show as ticks and crosses, and a failure opens inline under the line it is about. Runs use the unsaved text of open editors and read other files from disk.

Checking needs the `namespec` command. The extension uses the nearest `.venv` at or above the rule file (`.venv\Scripts\namespec.exe` on Windows, `.venv/bin/namespec` elsewhere), then `namespec` on `PATH`. Set **namespec.command** to use a different executable. Without one, highlighting and navigation still work and a single warning explains why examples are not checked. Nothing runs in Restricted Mode, because checking starts a program; trust the workspace to turn checks on.

## Install locally

From this directory, with Node.js and npm installed:

```powershell
npm ci
npm test
npm run package
code --install-extension ./namespec-0.6.0.vsix --force
```

Open a `.names` file. The language indicator should say **Namespec**. If the file was already open, use **Developer: Reload Window**. Existing explicit file-language associations can be changed with **Change Language Mode**.

The publisher ID `namespec-local` is for local development. This extension has not been published to the Marketplace yet; its public publisher identity is undecided. Like the Python package, it is MIT licensed.

## Development

Edit `syntaxes/namespec.tmLanguage.json` to adjust scopes and `language-configuration.json` for editing behavior. `definitions.cjs` indexes declaration/reference sites and preview ranges. `examples.cjs` finds and runs the `namespec` command and turns its `test --json` report into editor positions. `extension.cjs` registers the definition and hover providers, the diagnostics and the test controller. Run `npm test` for tokenizer, navigation, preview and example tests, then rebuild and reinstall the VSIX. The example tests use `../../.venv` when it exists, so run `uv sync` in the repository root first. The package includes the TextMate and Oniguruma runtime dependencies; packaging tools and tests are excluded.

To check activation, navigation and example checks inside a real extension host, run `code --extensionDevelopmentPath=<absolute-extension-directory> --extensionTestsPath=<absolute-extension-directory>/test/extension-host.cjs --disable-extensions --disable-workspace-trust --user-data-dir=<temporary-profile-directory> <empty-scratch-folder>`. The separate profile keeps the test session isolated from your normal editor. The scratch folder lets the test write a rule file, run it from the Testing view while it is closed, and delete it again; leave it off to skip that part.

VS Code documents [TextMate syntax highlighting](https://code.visualstudio.com/api/language-extensions/syntax-highlight-guide), [definition providers](https://code.visualstudio.com/api/language-extensions/programmatic-language-features#show-definitions-of-a-symbol), the [Testing API](https://code.visualstudio.com/api/extension-guides/testing), [extension host tests](https://code.visualstudio.com/api/working-with-extensions/testing-extension), and [local VSIX installation](https://code.visualstudio.com/docs/configure/extensions/extension-marketplace#_install-from-a-vsix).
