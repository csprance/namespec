const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { performance } = require("node:perf_hooks");
const vscode = require("vscode");

// Run with VS Code's --extensionDevelopmentPath and --extensionTestsPath flags.
async function run() {
  const extension = vscode.extensions.getExtension("namespec-local.namespec");
  assert.ok(extension);
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
}

module.exports = { run };
