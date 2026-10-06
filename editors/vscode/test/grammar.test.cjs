const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { before, test } = require("node:test");
const oniguruma = require("vscode-oniguruma");
const { Registry, parseRawGrammar, INITIAL } = require("vscode-textmate");

let grammar;
before(async () => {
  await oniguruma.loadWASM(fs.readFileSync(require.resolve("vscode-oniguruma/release/onig.wasm")));
  const grammarPath = path.join(__dirname, "../syntaxes/namespec.tmLanguage.json");
  const registry = new Registry({
    onigLib: Promise.resolve({
      createOnigScanner: (patterns) => new oniguruma.OnigScanner(patterns),
      createOnigString: (text) => new oniguruma.OnigString(text),
    }),
    loadGrammar: async () => parseRawGrammar(fs.readFileSync(grammarPath, "utf8"), grammarPath),
  });
  grammar = await registry.loadGrammar("source.namespec");
});

function scopesAt(line, token) {
  const offset = line.indexOf(token);
  assert.notEqual(offset, -1);
  return grammar.tokenizeLine(line, INITIAL).tokens.find(
    (item) => item.startIndex <= offset && item.endIndex > offset,
  ).scopes;
}

test("resource and field declarations use theme-aware scopes", () => {
  assert.ok(scopesAt("resource shot {", "shot").includes("entity.name.type.namespec"));
  const field = "version = integer minimum 1 padded to 3 digits";
  assert.ok(scopesAt(field, "version").includes("variable.other.property.namespec"));
  assert.ok(scopesAt(field, "integer").includes("storage.type.namespec"));
  assert.ok(scopesAt(field, "3").includes("constant.numeric.namespec"));
});

test("template slots have their own scope in either quote style", () => {
  for (const quote of ['"', "'"]) {
    const line = `name = ${quote}{asset_name}_v{version}.abc${quote} // explanation`;
    assert.ok(scopesAt(line, "asset_name").includes("variable.parameter.namespec"));
    assert.ok(scopesAt(line, "version").includes("variable.parameter.namespec"));
    assert.ok(scopesAt(line, "explanation").includes("comment.line.double-slash.namespec"));
  }
});

test("comments, regexes and examples do not become template slots", () => {
  assert.ok(scopesAt("// resource {name}", "name").includes("comment.line.double-slash.namespec"));
  const regex = 'sequence = text matching "[0-9]{3}"';
  assert.ok(scopesAt(regex, "3").includes("string.quoted.double.namespec"));
  assert.ok(!scopesAt(regex, "3").includes("constant.numeric.namespec"));
  const sample = 'input = "literal_{name}"';
  assert.ok(!scopesAt(sample, "name").includes("variable.parameter.namespec"));
  assert.ok(scopesAt('location = "//server/{job}/{name}"', "server").includes("string.quoted.template.namespec"));
});

test("escaped quotes stay inside strings and escaped braces are literal", () => {
  const line = String.raw`name = "prefix\"{asset_name}_{{literal}}" // after`;
  assert.ok(scopesAt(line, "asset_name").includes("variable.parameter.namespec"));
  assert.ok(!scopesAt(line, "literal").includes("variable.parameter.namespec"));
  assert.ok(scopesAt(line, "after").includes("comment.line.double-slash.namespec"));
});

test("both real schemas tokenize without leaving a string open", () => {
  for (const filename of ["assets.names", "studio.names"]) {
    const source = fs.readFileSync(path.join(__dirname, "../../../examples", filename), "utf8");
    let stack = INITIAL;
    for (const line of source.split(/\r?\n/)) {
      stack = grammar.tokenizeLine(line, stack).ruleStack;
    }
    assert.equal(stack.depth, 1, filename);
  }
});
