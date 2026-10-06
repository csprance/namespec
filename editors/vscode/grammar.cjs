const fs = require("node:fs/promises");
const path = require("node:path");
const oniguruma = require("vscode-oniguruma");
const { Registry, parseRawGrammar } = require("vscode-textmate");

let loaded;
function loadGrammar() {
  loaded ??= (async () => {
    await oniguruma.loadWASM(await fs.readFile(require.resolve("vscode-oniguruma/release/onig.wasm")));
    const filename = path.join(__dirname, "syntaxes/namespec.tmLanguage.json");
    const registry = new Registry({
      onigLib: Promise.resolve({
        createOnigScanner: (patterns) => new oniguruma.OnigScanner(patterns),
        createOnigString: (text) => new oniguruma.OnigString(text),
      }),
      loadGrammar: async () => parseRawGrammar(await fs.readFile(filename, "utf8"), filename),
    });
    return registry.loadGrammar("source.namespec");
  })();
  return loaded;
}

module.exports = { loadGrammar };
