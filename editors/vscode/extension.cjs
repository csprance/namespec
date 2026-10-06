const vscode = require("vscode");
const { loadGrammar } = require("./grammar.cjs");
const { indexDefinitions } = require("./definitions.cjs");

async function activate(context) {
  const grammar = await loadGrammar();
  const cache = new WeakMap();
  context.subscriptions.push(vscode.languages.registerDefinitionProvider("namespec", {
    provideDefinition(document, position, cancellation) {
      if (cancellation.isCancellationRequested) return [];
      let entry = cache.get(document);
      if (!entry || entry.version !== document.version) {
        entry = { version: document.version, lookup: indexDefinitions(document.getText(), grammar) };
        cache.set(document, entry);
      }
      const range = ({ start, end }) => new vscode.Range(document.positionAt(start), document.positionAt(end));
      return entry.lookup(document.offsetAt(position)).map(({ origin, target }) => ({
        originSelectionRange: range(origin),
        targetUri: document.uri,
        targetRange: range(target),
        targetSelectionRange: range(target),
      }));
    },
  }));
}

module.exports = { activate };
