const path = require("node:path");
const { TextDecoder } = require("node:util");
const vscode = require("vscode");
const { loadGrammar } = require("./grammar.cjs");
const { indexDefinitions } = require("./definitions.cjs");
const { findCommand, readReport, runExamples } = require("./examples.cjs");

async function activate(context) {
  activateExamples(context);
  const grammar = await loadGrammar();
  const cache = new WeakMap();
  const pending = new Map();
  function index(document) {
    let entry = cache.get(document);
    if (!entry || entry.version !== document.version) {
      entry = { version: document.version, lookup: indexDefinitions(document.getText(), grammar) };
      cache.set(document, entry);
    }
    return entry.lookup;
  }
  function cancel(document) {
    clearTimeout(pending.get(document));
    pending.delete(document);
  }
  function warm(document) {
    if (document.languageId === "namespec" && !document.isClosed) index(document);
  }
  function changed({ document }) {
    if (document.languageId !== "namespec") return;
    cancel(document);
    pending.set(document, setTimeout(() => {
      pending.delete(document);
      warm(document);
    }, 75));
  }
  function lookup(document, position, cancellation) {
    if (cancellation.isCancellationRequested) return [];
    // A click during the edit debounce still uses the latest document version.
    cancel(document);
    return index(document)(document.offsetAt(position));
  }
  const range = (document, { start, end }) => new vscode.Range(document.positionAt(start), document.positionAt(end));
  const fullRange = (document, target) => range(document, {
    start: target.rangeStart ?? target.start,
    end: target.rangeEnd ?? target.end,
  });
  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument(warm),
    vscode.workspace.onDidChangeTextDocument(changed),
    vscode.workspace.onDidCloseTextDocument((document) => { cancel(document); cache.delete(document); }),
    { dispose() { for (const document of pending.keys()) cancel(document); } },
    vscode.languages.registerDefinitionProvider("namespec", {
      provideDefinition(document, position, cancellation) {
        return lookup(document, position, cancellation).map(({ origin, target }) => ({
          originSelectionRange: range(document, origin),
          targetUri: document.uri,
          targetRange: fullRange(document, target),
          targetSelectionRange: range(document, target),
        }));
      },
    }),
    vscode.languages.registerHoverProvider("namespec", {
      provideHover(document, position, cancellation) {
        const links = lookup(document, position, cancellation);
        if (!links.length) return undefined;
        const contents = links.map(({ target }) => new vscode.MarkdownString().appendCodeblock(
          document.getText(fullRange(document, target)), "namespec",
        ));
        return new vscode.Hover(contents, range(document, links[0].origin));
      },
    }),
  );
  for (const document of vscode.workspace.textDocuments) warm(document);
}

// Examples run through the namespec command: underlined while typing, and listed as tests
// with a gutter run button. Without the command, highlighting and navigation still work.
function activateExamples(context) {
  const log = vscode.window.createOutputChannel("Namespec", { log: true });
  const problems = vscode.languages.createDiagnosticCollection("namespec");
  const controller = vscode.tests.createTestController("namespec", "Namespec");
  const pending = new Map();
  const running = new Map();
  let warned = false;

  const toRange = ({ start, end }) => new vscode.Range(start.line, start.character, end.line, end.character);
  const isRules = (document) => document.languageId === "namespec";
  const openDocument = (uri) => vscode.workspace.textDocuments.find((document) => document.uri.toString() === uri.toString());

  async function check(uri, text, signal) {
    if (!vscode.workspace.isTrusted) throw new Error("Namespec only runs examples in a trusted workspace.");
    const folder = vscode.workspace.getWorkspaceFolder(uri) ?? vscode.workspace.workspaceFolders?.[0];
    const directory = uri.scheme === "file" ? path.dirname(uri.fsPath) : folder?.uri.fsPath;
    const command = findCommand(directory, vscode.workspace.getConfiguration("namespec", uri).get("command"));
    return readReport(await runExamples(command, text, { cwd: directory, signal }), text);
  }

  function unavailable(error) {
    log.error(error.message);
    if (warned) return;
    warned = true;
    const message = error.code === "ENOENT"
      ? "Namespec examples are not checked: the namespec command was not found. Install the Python package or set namespec.command."
      : `Namespec examples are not checked: ${error.message}`;
    vscode.window.showWarningMessage(message, "Open Settings").then((choice) => {
      if (choice) vscode.commands.executeCommand("workbench.action.openSettings", "namespec.command");
    });
  }

  function fileItem(uri) {
    let item = controller.items.get(uri.toString());
    if (!item) {
      item = controller.createTestItem(uri.toString(), vscode.workspace.asRelativePath(uri), uri);
      item.canResolveChildren = true;
      controller.items.add(item);
    }
    return item;
  }

  function publish(uri, result) {
    problems.set(uri, result.problems.map(({ code, message, range }) => {
      const diagnostic = new vscode.Diagnostic(toRange(range), message, vscode.DiagnosticSeverity.Error);
      diagnostic.source = "namespec";
      diagnostic.code = code;
      return diagnostic;
    }));
    // Rules that do not load keep their last known examples instead of losing every test.
    if (!result.loaded) return;
    const parent = fileItem(uri);
    parent.canResolveChildren = false;
    parent.children.replace(result.examples.map((example) => {
      const item = parent.children.get(example.id) ?? controller.createTestItem(example.id, example.label, uri);
      item.range = toRange(example.range);
      return item;
    }));
  }

  async function live(document) {
    const key = document.uri.toString();
    running.get(key)?.abort();
    const abort = new AbortController();
    running.set(key, abort);
    const version = document.version;
    try {
      const result = await check(document.uri, document.getText(), abort.signal);
      if (!document.isClosed && document.version === version) publish(document.uri, result);
    } catch (error) {
      if (error.name !== "AbortError") unavailable(error);
    } finally {
      if (running.get(key) === abort) running.delete(key);
    }
  }

  function schedule(document, delay = 300) {
    if (!isRules(document) || document.isClosed || !vscode.workspace.isTrusted) return;
    // Diff views and other virtual documents are not the rules being edited.
    if (!["file", "untitled"].includes(document.uri.scheme)) return;
    const key = document.uri.toString();
    clearTimeout(pending.get(key));
    pending.set(key, setTimeout(() => {
      pending.delete(key);
      live(document);
    }, delay));
  }

  function forget(document) {
    const key = document.uri.toString();
    clearTimeout(pending.get(key));
    pending.delete(key);
    running.get(key)?.abort();
    problems.delete(document.uri);
    if (document.uri.scheme !== "file") controller.items.delete(key);
  }

  async function discover() {
    for (const uri of await vscode.workspace.findFiles("**/*.names", "**/{node_modules,.venv}/**")) fileItem(uri);
  }

  async function textOf(uri) {
    return openDocument(uri)?.getText() ?? new TextDecoder().decode(await vscode.workspace.fs.readFile(uri));
  }

  async function runTests(request, cancellation) {
    const run = controller.createTestRun(request);
    const excluded = new Set(request.exclude ?? []);
    const files = new Map();
    const select = (item) => {
      const parent = item.parent ?? item;
      const entry = files.get(parent.id) ?? { parent, all: false, only: new Set() };
      if (item === parent) entry.all = true;
      else entry.only.add(item.id);
      files.set(parent.id, entry);
    };
    if (request.include) request.include.forEach(select);
    else controller.items.forEach(select);
    for (const { parent, all, only } of files.values()) {
      if (cancellation.isCancellationRequested) break;
      if (excluded.has(parent)) continue;
      const chosen = () => {
        const items = [];
        parent.children.forEach((item) => {
          if ((all || only.has(item.id)) && !excluded.has(item)) items.push(item);
        });
        return items.length ? items : [parent];
      };
      let result;
      try {
        result = await check(parent.uri, await textOf(parent.uri));
      } catch (error) {
        unavailable(error);
        for (const item of chosen()) run.errored(item, new vscode.TestMessage(error.message));
        continue;
      }
      publish(parent.uri, result);
      const located = (problem) => {
        const message = new vscode.TestMessage(problem.message);
        message.location = new vscode.Location(parent.uri, toRange(problem.range));
        return message;
      };
      if (!result.loaded) {
        for (const item of chosen()) run.errored(item, result.problems.map(located));
        continue;
      }
      const outcomes = new Map(result.examples.map((example) => [example.id, example]));
      for (const item of chosen()) {
        const example = outcomes.get(item.id);
        if (!example) continue;
        if (example.passed) run.passed(item);
        else run.failed(item, example.failures.map(located));
      }
    }
    run.end();
  }

  controller.createRunProfile("Run", vscode.TestRunProfileKind.Run, runTests, true);
  controller.resolveHandler = async (item) => {
    if (!item) return discover();
    if (!vscode.workspace.isTrusted) return;
    try {
      publish(item.uri, await check(item.uri, await textOf(item.uri)));
    } catch (error) {
      unavailable(error);
      item.error = error.message;
    }
  };
  controller.refreshHandler = discover;

  const watcher = vscode.workspace.createFileSystemWatcher("**/*.names");
  const recheckAll = () => vscode.workspace.textDocuments.forEach((document) => schedule(document, 0));
  context.subscriptions.push(
    log,
    problems,
    controller,
    watcher,
    watcher.onDidCreate((uri) => { if (!uri.fsPath.includes(`${path.sep}node_modules${path.sep}`)) fileItem(uri); }),
    watcher.onDidDelete((uri) => { controller.items.delete(uri.toString()); problems.delete(uri); }),
    vscode.workspace.onDidOpenTextDocument((document) => schedule(document, 0)),
    vscode.workspace.onDidChangeTextDocument(({ document }) => schedule(document)),
    vscode.workspace.onDidCloseTextDocument(forget),
    vscode.workspace.onDidGrantWorkspaceTrust(recheckAll),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (!event.affectsConfiguration("namespec.command")) return;
      warned = false;
      recheckAll();
    }),
    { dispose() { for (const abort of running.values()) abort.abort(); for (const timer of pending.values()) clearTimeout(timer); } },
  );
  recheckAll();
}

module.exports = { activate };
