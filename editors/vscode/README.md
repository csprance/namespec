# Namespec for VS Code

Syntax highlighting for `.names` files: resource declarations, field definitions, keywords, numbers, quoted strings, template placeholders, and `//` comments. Uses your current editor theme, with bracket matching, quote completion, indentation, and the Toggle Line Comment command.

Ctrl+click a reference (Cmd+click on macOS), press F12, or use **Go to Definition** to jump within the current file:

- `{field}` in a name or location template jumps to its field rule.
- `{name}` in a location jumps to that resource's `name` assignment.
- Resource names after `example` or `reject` jump to the resource declaration.
- Expected field names in `expect { ... }` jump to their field rules.
- `readers` in `reader = readers[filetype]` jumps to the mapping block; `filetype` jumps to its field rule.

Definitions can appear before or after references, and navigation follows unsaved edits. Comments, ordinary strings, and escaped template braces do not create links. Undefined references have no target; duplicate declarations offer multiple targets. Navigation uses a small JavaScript provider and the same TextMate tokenizer as highlighting, with no Python runtime requirement. Validate naming rules with the Namespec Python package; parser diagnostics and semantic completion are not provided by this extension.

## Install locally

From this directory, with Node.js and npm installed:

```powershell
npm ci
npm test
npm run package
code --install-extension ./namespec-0.2.0.vsix --force
```

Open a `.names` file. The language indicator should say **Namespec**. If the file was already open, use **Developer: Reload Window**. Existing explicit file-language associations can be changed with **Change Language Mode**.

The publisher ID `namespec-local` is for local development. This extension has not been published to the Marketplace. Its release license and public publisher identity are undecided.

## Development

Edit `syntaxes/namespec.tmLanguage.json` to adjust scopes and `language-configuration.json` for editing behavior. `definitions.cjs` indexes declaration/reference sites, and `extension.cjs` registers VS Code's definition provider. Run `npm test` for tokenizer and navigation tests, then rebuild and reinstall the VSIX. The package includes the TextMate and Oniguruma runtime dependencies; packaging tools and tests are excluded.

To check activation and navigation inside a real extension host, run `code --extensionDevelopmentPath=<absolute-extension-directory> --extensionTestsPath=<absolute-extension-directory>/test/extension-host.cjs --disable-extensions --user-data-dir=<temporary-profile-directory>`. The separate profile keeps the test session isolated from your normal editor.

VS Code documents [TextMate syntax highlighting](https://code.visualstudio.com/api/language-extensions/syntax-highlight-guide), [definition providers](https://code.visualstudio.com/api/language-extensions/programmatic-language-features#show-definitions-of-a-symbol), [extension host tests](https://code.visualstudio.com/api/working-with-extensions/testing-extension), and [local VSIX installation](https://code.visualstudio.com/docs/configure/extensions/extension-marketplace#_install-from-a-vsix).
