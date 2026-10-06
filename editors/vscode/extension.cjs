const vscode = require("vscode");
const { loadGrammar } = require("./grammar.cjs");
const { indexDefinitions } = require("./definitions.cjs");

async function activate(context) {
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

module.exports = { activate };
