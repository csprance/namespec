const assert = require("node:assert/strict");
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
  console.log("Namespec extension host: activation, definition links, unsaved edits and comments passed.");
}

module.exports = { run };
