# Namespec for VS Code

Edit `.names` rule files with syntax highlighting, declaration previews, navigation, and example checks while you type. The extension uses the Namespec Python command for validation, so the editor and command line apply the same rules.

New to the language? Follow the [Namespec guide](../../docs/guide.md) alongside this page. The [reference](../../docs/reference.md) covers every construct and diagnostic.

## What you need

| What you want to do | Requirements |
| --- | --- |
| Install a supplied VSIX and use highlighting, hover, and navigation | VS Code 1.85 or newer |
| Check rules and run their examples | The Namespec Python command; the setup below uses Python 3.10 or newer and uv |
| Build the extension from this checkout | Node.js 22 or newer and npm |

Installing a supplied VSIX does not require Node.js or npm. Python is needed for example checking, but highlighting and navigation work without it.

The instructions below assume you have the Namespec repository on your computer. Start in its root folder, the one containing `pyproject.toml`, `examples`, and `editors`.

## Install with a VS Code task

Open the **Namespec repository folder** in VS Code, then choose **Terminal > Run Task > Namespec: Install VS Code tooling**. The [task](../../.vscode/tasks.json) sets up the Python checker with `uv sync --locked --inexact`, preserving any additional packages already in `.venv`, installs the locked npm dependencies, runs the editor tests, builds a fresh `editors/vscode/namespec.vsix`, and installs it with the VS Code CLI. Each step must succeed before the next runs.

You need uv, Node.js 22 or newer, npm, and the `code` command on `PATH`. On macOS, use **Shell Command: Install 'code' command in PATH** from the Command Palette if needed. After installation, run **Developer: Reload Window**, then open `examples/guide.names` to use highlighting, navigation, hovers, and live checks.

The task also works when Namespec is a folder in a multi-root workspace. Opening only a parent folder does not expose nested `.vscode/tasks.json` files; open Namespec directly or add it with **File > Add Folder to Workspace**. Rerun the task after editing the extension to rebuild and reinstall it. For manual setup or a supplied VSIX, follow the steps below.

## 1. Set up the example checker

Open the repository folder in VS Code. In its terminal, run:

```sh
uv sync --locked
uv run --locked namespec examples/guide.names test
```

The first command creates the repository's `.venv` and installs Namespec. The second checks the supplied guide. It should print:

```text
9 passed
```

Keep this environment beside the repository. The extension finds its `namespec` executable automatically for rule files inside the repository, including files under `examples`. You do not need to activate the environment in a terminal.

For Python and uv installation, or using Namespec in another project, see the [setup in the guide](../../docs/guide.md).

## 2. Install the extension

Namespec is distributed as a local VSIX rather than a Marketplace installation. Choose the route that matches what you have.

### If you have a VSIX file

1. Open VS Code's **Extensions** view.
2. Open the view's **…** menu and choose **Install from VSIX…**.
3. Select the supplied `.vsix` file.
4. Run **Developer: Reload Window** from the Command Palette if an already-open `.names` file has not picked up the extension.

You can also install it from a terminal in the directory containing the file:

```sh
code --install-extension ./namespec-0.6.1.vsix --force
```

Use your actual filename if it differs. If `code` is not on your terminal's `PATH`, use the Extensions view. See VS Code's [VSIX installation instructions](https://code.visualstudio.com/docs/configure/extensions/extension-marketplace#_install-from-a-vsix).

### If you are working from source

Build a VSIX from the checkout you intend to use. From the repository root:

```sh
cd editors/vscode
npm ci
npm test
npm run package
code --install-extension ./namespec-0.6.1.vsix --force
cd ../..
```

`npm run package` creates `editors/vscode/namespec-0.6.1.vsix`. If you prefer, install that file through the Extensions view instead of the `code` command.

Rebuild and reinstall after changing the extension's source. An existing VSIX does not automatically pick up later edits in the checkout.

## 3. Try a live check

Open [`examples/guide.names`](../../examples/guide.names). The language indicator in the bottom-right corner should say **Namespec**. If it does not, click the indicator and choose **Namespec**, or run **Change Language Mode**.

Example checking starts a local program. It runs only in a trusted workspace; highlighting and navigation also work in Restricted Mode. Use **Workspaces: Manage Workspace Trust** to review the folder's trust setting. VS Code explains this in [Workspace Trust](https://code.visualstudio.com/docs/editing/workspaces/workspace-trust).

Try a small edit in the first `example model` block:

1. Leave its input as `"Donut_high_v004.abc"`.
2. In its `expect` block, change only `lod = "high"` to `lod = "mid"`.
3. Pause typing. The changed expectation should be underlined, and **View > Problems** should show `Expected lod = "mid", got "high".`
4. Change the expectation back to `"high"`. The problem disappears.

You do not need to save for these checks. Open editors are checked from their current, unsaved text. Terminal commands read the saved file, so save before comparing their results.

The underlines tell you where to look:

| Problem | What gets underlined |
| --- | --- |
| An expected value differs from the parsed value | That field in `expect` |
| An input fails to parse, or a `reject` input is accepted | The input string |
| `expect` leaves out a field present in the parsed result | The `expect { ... }` block |
| A rule cannot load, such as an unknown field, invalid sample, or syntax error | The relevant declaration |

An `example` asserts that an input is accepted with the exact expected fields. A `reject` asserts that an input fails with the specified diagnostic. A correctly rejected name is a passing test.

## 4. Run examples deliberately

Open the **Testing** view, marked with a beaker icon, or use the run button beside an `example` or `reject` block.

- Run an individual example from its gutter button.
- Run a file from its entry in the Testing view.
- Use **Run Tests** in the Testing view to run the discovered files.
- Use **Refresh Tests** to discover `.names` files in the workspace. Expand a file to load its examples.

Test runs show passing and failing results. A failure opens a message at the relevant line. Open documents use their unsaved text; closed files are read from disk. Cancelling a run stops its active command. An older result cannot replace diagnostics for a newer edit.

Live checks update Problems while you type. Run the tests to refresh their recorded pass/fail results in the Testing view. VS Code's [testing guide](https://code.visualstudio.com/docs/debugtest/testing) explains the standard controls.

The equivalent command from the repository root is:

```sh
uv run --locked namespec examples/guide.names test
```

For a separate filename you want to investigate, use `inspect`:

```sh
uv run --locked namespec examples/guide.names inspect Donut_high_v004.abc
```

To build your own rule file and add examples, continue with the [Namespec guide](../../docs/guide.md).

## 5. Navigate the rules

Hover over a declaration or reference to preview its complete rule. Ctrl+click on Windows/Linux, Cmd+click on macOS, or **Go to Definition** (F12) jumps to the declaration. Hold Ctrl while hovering for VS Code's definition preview. **Peek Definition** opens it inline; the default Windows shortcut is Alt+F12. Escape closes Peek.

| Reference | Destination |
| --- | --- |
| `{field}` in a resource template, including inside an optional group | The field's rule |
| `{part}` inside a composite such as `Shot = "{Sequence}_{shotnum}"` | The component field's rule |
| `{name}` in a location | That resource's `name` assignment |
| `{root}` in a location | The `roots` block |
| A resource name after `example` or `reject` | The resource declaration, including its metadata |
| A field name in `expect { ... }` | The field's rule |
| `readers` in `reader = readers[filetype]` | The reader mapping block |
| `filetype` in that reader expression | The selector field's rule |

Declarations can appear before or after references, share a line, or span several lines. Navigation and hover follow unsaved changes. They work within the current file, matching the language's lack of imports.

Comments, ordinary strings, and escaped template braces do not create links. Templates use `{{` and `}}` for literal braces, and `[[` and `]]` for literal brackets. Undefined references have no destination; duplicate declarations can offer several destinations while validation reports the duplicate.

Highlighting uses your editor theme. The extension also supports bracket matching, quote completion, indentation, and **Toggle Line Comment**. Semantic field-name completion is not provided.

## 6. Choose a different Python environment

For each rule file, the extension chooses a command in this order:

1. The **Namespec: Command** setting, if supplied.
2. The nearest `.venv` containing a Namespec executable, searching from the rule file's directory up through its parents.
3. `namespec` on the VS Code process's `PATH`.

The executable is `.venv/Scripts/namespec.exe` on Windows and `.venv/bin/namespec` on Linux/macOS. For an untitled buffer, the search starts from the workspace folder when available. Saving the buffer gives it an explicit directory to search from.

If your rules live elsewhere, open Settings, search for **namespec.command**, and set the full executable path. For example, in workspace settings on Windows:

```json
{
  "namespec.command": "C:/work/namespec/.venv/Scripts/namespec.exe"
}
```

On Linux/macOS, use a path such as `/home/you/namespec/.venv/bin/namespec`. This setting accepts an executable path, not a shell command such as `uv run namespec` or a string containing arguments. The extension supplies its own arguments and sends the rule text on standard input.

The editor uses the default `test` behavior. It does not add the CLI's `--strict` or `--filesystem` options. Use the command line for those additional policies.

## Troubleshooting

| What you see | What to check |
| --- | --- |
| The file looks like plain text | Confirm the extension is enabled and the language mode is **Namespec**. Reload the window after installation. An explicit file association can override the `.names` extension. |
| Highlighting works, but examples are not checked | Confirm the workspace is trusted and the Python checker is installed. Look for a warning or open **View > Output** and select **Namespec**. |
| “The namespec command was not found” | Run `uv sync --locked` in the repository root, then confirm the rules are beneath that root. Otherwise set **namespec.command** to the installed executable. |
| The command fails or produces no report | Open the **Namespec** output channel for the error, then run the checker in a terminal. Confirm the configured executable is from this Namespec package and supports `test --json`. |
| Terminal and editor results differ | Save the file first. Check that both use the same Python environment; a configured command takes precedence over automatic `.venv` discovery. |
| No examples appear in Testing | Open a rule file or refresh and expand its entry. It needs `example` or `reject` blocks, and the rules must load successfully. |
| Old examples remain after breaking a declaration | Fix the rule-loading error first. The extension retains the last known examples until it can load the file again. |
| A long check is interrupted | Checks have a 15-second subprocess timeout. Run the file in a terminal and investigate expensive patterns or an unexpectedly large example set. |
| Source edits have no effect on the installed extension | Build a new VSIX, reinstall it, and reload the window. |

## Maintaining the extension

The [development guide](../../developer.md) covers the Python environment and repository checks. The extension's local publisher ID is `namespec-local`; it has not been published to the Marketplace, and its public publisher identity is undecided. The extension and Python package are MIT licensed.

| File | Responsibility |
| --- | --- |
| `syntaxes/namespec.tmLanguage.json` | TextMate highlighting and template contexts |
| `language-configuration.json` | Comments, brackets, quotes, and indentation |
| `definitions.cjs` | Declaration/reference indexing and preview ranges |
| `examples.cjs` | Executable discovery, CLI execution, and report positions |
| `extension.cjs` | Providers, diagnostics, and Testing view integration |

Run `npm test` from this directory. The suite includes tokenizer, navigation, report, and controller lifecycle checks. Its Python integration test uses the repository's `.venv` when available, so set up that environment first to exercise the integration. The packaged extension includes TextMate and Oniguruma; it excludes development dependencies and tests.

For acceptance in a real VS Code extension host, use an isolated profile and an empty scratch folder:

```sh
code --extensionDevelopmentPath=<absolute-extension-directory> --extensionTestsPath=<absolute-extension-directory>/test/extension-host.cjs --disable-extensions --disable-workspace-trust --user-data-dir=<temporary-profile-directory> <empty-scratch-folder>
```

Replace the placeholders with actual paths, quoting paths containing spaces. This development-only command disables trust prompts in the isolated test window. The test checks activation, navigation, hover, unsaved edits, and live diagnostics. It also creates, checks, and deletes a temporary rule file in the scratch folder to test closed-file execution; omit the scratch folder to skip that part.

Implementation references: [TextMate syntax highlighting](https://code.visualstudio.com/api/language-extensions/syntax-highlight-guide), [definition providers](https://code.visualstudio.com/api/language-extensions/programmatic-language-features#show-definitions-of-a-symbol), [Testing API](https://code.visualstudio.com/api/extension-guides/testing), and [extension host tests](https://code.visualstudio.com/api/working-with-extensions/testing-extension).
