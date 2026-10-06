# Namespec for VS Code

Syntax highlighting for `.names` files: resource declarations, field definitions, keywords, numbers, quoted strings, template placeholders, and `//` comments. Uses your current editor theme, with bracket matching, quote completion, indentation, and the Toggle Line Comment command.

This is a declarative language extension with no executable extension code or Python runtime requirement. It supplies highlighting, not parser diagnostics, go-to-definition, or semantic completion. Validate naming rules with the Namespec Python package and its tests.

## Install locally

From this directory, with Node.js and npm installed:

```powershell
npm ci
npm test
npm run package
code --install-extension ./namespec-0.1.0.vsix
```

Open a `.names` file. The language indicator should say **Namespec**. If the file was already open, use **Developer: Reload Window**. Existing explicit file-language associations can be changed with **Change Language Mode**.

The publisher ID `namespec-local` is for local development. This extension has not been published to the Marketplace. Its release license and public publisher identity are undecided.

## Development

Edit `syntaxes/namespec.tmLanguage.json` to adjust scopes and `language-configuration.json` for editing behavior. Run `npm test` to exercise the grammar with VS Code's TextMate tokenizer, then rebuild and reinstall the VSIX. Node dependencies are development tools only and are excluded from the packaged extension.

VS Code documents [TextMate syntax highlighting](https://code.visualstudio.com/api/language-extensions/syntax-highlight-guide) and [local VSIX installation](https://code.visualstudio.com/docs/configure/extensions/extension-marketplace#_install-from-a-vsix).
