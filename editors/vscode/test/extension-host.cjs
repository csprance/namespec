const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { performance } = require("node:perf_hooks");
const vscode = require("vscode");

const { VENV } = require("../examples.cjs");

const CLI = path.join(__dirname, "../../..", ...VENV);
const GUIDE = fs.readFileSync(path.join(__dirname, "../../../examples/guide.names"), "utf8");
const BROKEN = GUIDE.replace('lod = "high" version = 4', 'lod = "mid" version = 4');

function diagnostics(uri, accept, timeout = 15000) {
  return new Promise((resolve, reject) => {
    const settle = () => {
      const found = vscode.languages.getDiagnostics(uri);
      if (!accept(found)) return;
      finish();
      resolve(found);
    };
    const listener = vscode.languages.onDidChangeDiagnostics(({ uris }) => {
      if (uris.some((changed) => changed.toString() === uri.toString())) settle();
    });
    const timer = setTimeout(() => {
      finish();
      reject(new Error(`no matching diagnostics for ${uri}`));
    }, timeout);
    const finish = () => { listener.dispose(); clearTimeout(timer); };
    settle();
  });
}

// Live checks underline an unsaved buffer; a test run reads a closed file from disk. The
// run half needs a scratch folder passed as the last argument so the file can be found.
async function examples() {
  const document = await vscode.workspace.openTextDocument({ language: "namespec", content: BROKEN });
  const [failure] = await diagnostics(document.uri, (found) => found.length > 0);
  assert.equal(failure.message, 'Expected lod = "mid", got "high".');
  assert.equal(failure.source, "namespec");
  assert.equal(document.getText(failure.range), 'lod = "mid"');
  const fix = new vscode.WorkspaceEdit();
  fix.replace(document.uri, failure.range, 'lod = "high"');
  assert.ok(await vscode.workspace.applyEdit(fix));
  await diagnostics(document.uri, (found) => found.length === 0);

  const folder = vscode.workspace.workspaceFolders?.[0]?.uri;
  if (!folder) return "live checks";
  const rules = vscode.Uri.joinPath(folder, `broken-${process.pid}.names`);
  await vscode.workspace.fs.writeFile(rules, Buffer.from(BROKEN.replace(/\r?\n/g, "\r\n")));
  try {
    await vscode.commands.executeCommand("testing.refreshTests");
    await vscode.commands.executeCommand("testing.runAll");
    const [ran] = await diagnostics(rules, (found) => found.length > 0);
    assert.equal(ran.message, 'Expected lod = "mid", got "high".');
    assert.equal(vscode.workspace.textDocuments.some((open) => open.uri.toString() === rules.toString()), false);
  } finally {
    await vscode.workspace.fs.delete(rules);
  }
  return "live checks and a test run";
}

// Run with VS Code's --extensionDevelopmentPath and --extensionTestsPath flags.
async function run() {
  const extension = vscode.extensions.getExtension("namespec-local.namespec");
  assert.ok(extension);
  if (fs.existsSync(CLI)) {
    await vscode.workspace.getConfiguration("namespec").update("command", CLI, vscode.ConfigurationTarget.Global);
  }
  await extension.activate();
  const document = await vscode.workspace.openTextDocument({
    language: "namespec",
    content: 'item = text matching "[a-z]+"\r\nresource thing { name = "{item}" location = "/data/{name}" }',
  });
  async function definition(reference) {
    const position = document.positionAt(document.getText().indexOf(reference) + 2);
    const links = await vscode.commands.executeCommand("vscode.executeDefinitionProvider", document.uri, position);
    assert.equal(links.length, 1, reference);
    const link = links[0];
    assert.equal((link.targetUri ?? link.uri).toString(), document.uri.toString());
    assert.ok(document.getText(link.targetRange ?? link.range).includes("="));
    return link.targetSelectionRange ?? link.range;
  }
  assert.equal((await definition("{item}")).start.line, 0);
  assert.equal(document.getText(await definition("{name}")), "name");

  const edit = new vscode.WorkspaceEdit();
  edit.insert(document.uri, new vscode.Position(0, 0), "// unsaved edit\r\n");
  assert.ok(await vscode.workspace.applyEdit(edit));
  assert.equal((await definition("{item}")).start.line, 1);
  const origin = document.getText().indexOf("unsaved");
  const none = await vscode.commands.executeCommand("vscode.executeDefinitionProvider", document.uri, document.positionAt(origin));
  assert.equal(none.length, 0);

  async function hover(reference) {
    const position = document.positionAt(document.getText().indexOf(reference) + 2);
    const hovers = await vscode.commands.executeCommand("vscode.executeHoverProvider", document.uri, position);
    assert.equal(hovers.length, 1);
    assert.notEqual(hovers[0].contents[0].isTrusted, true);
    return hovers[0].contents[0].value;
  }
  assert.match(await hover("{item}"), /```namespec\s+item = text matching "\[a-z\]\+"\s+```/);
  const nameHover = await hover("{name}");
  assert.ok(nameHover.includes('name = "{item}"'));
  assert.ok(!nameHover.includes("location"));
  const replace = new vscode.WorkspaceEdit();
  const fieldStart = document.getText().indexOf('item =');
  replace.replace(document.uri, new vscode.Range(document.positionAt(fieldStart), document.positionAt(fieldStart + 'item = text matching "[a-z]+"'.length)), 'item = one of "alpha", "beta"');
  assert.ok(await vscode.workspace.applyEdit(replace));
  assert.ok((await hover("{item}")).includes('item = one of "alpha", "beta"'));

  const studio = await vscode.workspace.openTextDocument({
    language: "namespec",
    content: fs.readFileSync(path.join(__dirname, "../../../examples/studio.names"), "utf8"),
  });
  const position = studio.positionAt(studio.getText().indexOf("{jobnum}") + 2);
  const timings = {};
  for (const [label, command] of [["definition", "vscode.executeDefinitionProvider"], ["hover", "vscode.executeHoverProvider"]]) {
    const samples = [];
    for (let i = 0; i < 25; i++) {
      const start = performance.now();
      assert.equal((await vscode.commands.executeCommand(command, studio.uri, position)).length, 1);
      samples.push(performance.now() - start);
    }
    timings[label] = { firstMs: samples[0], medianMs: samples.sort((a, b) => a - b)[12] };
  }
  console.log(`Namespec extension host timings: ${JSON.stringify(timings)}`);
  console.log("Namespec extension host: activation, definition previews, highlighted hover payloads, unsaved edits and comments passed.");
  if (fs.existsSync(CLI)) console.log(`Namespec extension host: ${await examples()} passed.`);
  else console.log(`Namespec extension host: examples skipped, ${CLI} is missing.`);
}

module.exports = { run };
