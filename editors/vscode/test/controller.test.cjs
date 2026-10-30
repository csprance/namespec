const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");
const { readReport } = require("../examples.cjs");

const disposable = () => ({ dispose() {} });
const tick = () => new Promise((resolve) => setImmediate(resolve));
const report = (input = "x", message) => ({ examples: [{
  kind: "example", resource: "item", source: "name", input, passed: !message, span: [0, 1],
  failures: message ? [{ code: "example_failed", message, span: [0, 1] }] : [],
}] });

function collection(owner) {
  const entries = new Map();
  return {
    get size() { return entries.size; },
    get: (id) => entries.get(id),
    add(item) { item.parent = owner; entries.set(item.id, item); },
    delete: (id) => entries.delete(id),
    replace(items) { entries.clear(); items.forEach((item) => this.add(item)); },
    forEach: (fn) => entries.forEach(fn),
  };
}

// Exercise the registered VS Code callbacks with controlled subprocess completion,
// without launching an editor or duplicating the controller's implementation.
async function harness() {
  const events = new Map();
  const on = (name) => (handler) => {
    const handlers = events.get(name) ?? [];
    handlers.push(handler);
    events.set(name, handlers);
    return disposable();
  };
  const emit = (name, value) => (events.get(name) ?? []).forEach((handler) => handler(value));
  const publications = [], commands = [], warnings = [], runs = [], timers = new Map();
  let timerId = 0;
  const controller = {
    items: collection(),
    createTestItem(id, label, uri) { const item = { id, label, uri }; item.children = collection(item); return item; },
    createRunProfile(name, kind, callback) { this.run = callback; },
    createTestRun() {
      const run = { results: [], ended: false };
      for (const status of ["passed", "failed", "errored"]) run[status] = (item) => run.results.push([status, item]);
      run.end = () => { run.ended = true; };
      runs.push(run);
      return run;
    },
    dispose() {},
  };
  const workspace = {
    isTrusted: true, textDocuments: [],
    getWorkspaceFolder: () => undefined,
    getConfiguration: () => ({ get: () => "namespec" }),
    asRelativePath: (uri) => uri.fsPath,
    findFiles: async () => [],
    fs: { readFile: async () => Buffer.from("disk") },
    onDidOpenTextDocument: on("open"), onDidChangeTextDocument: on("change"),
    onDidCloseTextDocument: on("close"), onDidGrantWorkspaceTrust: on("trust"),
    onDidChangeConfiguration: on("configuration"),
    createFileSystemWatcher: () => ({
      onDidCreate: on("create"), onDidChange: on("fileChange"), onDidDelete: on("delete"), dispose() {},
    }),
  };
  const vscode = {
    workspace,
    window: {
      createOutputChannel: () => ({ error() {}, dispose() {} }),
      showWarningMessage: async (message) => { warnings.push(message); },
    },
    languages: {
      createDiagnosticCollection: () => ({
        set(uri, problems) { publications.push({ uri, problems }); }, delete() {}, dispose() {},
      }),
      registerDefinitionProvider: disposable, registerHoverProvider: disposable,
    },
    tests: { createTestController: () => controller },
    Range: class { constructor(...args) { this.args = args; } },
    Diagnostic: class { constructor(range, message) { this.range = range; this.message = message; } },
    TestMessage: class { constructor(message) { this.message = message; } },
    Location: class {}, DiagnosticSeverity: { Error: 0 }, TestRunProfileKind: { Run: 0 },
  };
  const module = { exports: {} };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../extension.cjs"), "utf8"), {
    module, AbortController,
    setTimeout(fn, delay) { timers.set(++timerId, { fn, delay }); return timerId; },
    clearTimeout: (id) => timers.delete(id),
    require(name) {
      if (name === "vscode") return vscode;
      if (name === "./grammar.cjs") return { loadGrammar: async () => ({}) };
      if (name === "./definitions.cjs") return { indexDefinitions: () => () => [] };
      if (name === "./examples.cjs") return {
        findCommand: () => "namespec", readReport,
        runExamples(command, text, { signal } = {}) {
          return new Promise((resolve, reject) => {
            const abort = () => reject(Object.assign(new Error("Cancelled"), { name: "AbortError" }));
            signal?.addEventListener("abort", abort, { once: true });
            commands.push({ text, signal, resolve, reject });
            if (signal?.aborted) abort();
          });
        },
      };
      return require(name);
    },
  });
  const context = { subscriptions: [] };
  await module.exports.activate(context);
  function document(filename = "test.names") {
    const uri = { scheme: "file", fsPath: path.join(__dirname, filename), toString() { return this.fsPath; } };
    const item = { uri, version: 1, languageId: "namespec", isClosed: false, text: "old", getText() { return this.text; } };
    workspace.textDocuments.push(item);
    emit("create", uri);
    return item;
  }
  function cancellation() {
    const handlers = new Set();
    return {
      isCancellationRequested: false,
      onCancellationRequested(handler) { handlers.add(handler); return { dispose: () => handlers.delete(handler) }; },
      cancel() { this.isCancellationRequested = true; handlers.forEach((fn) => fn()); },
      get listeners() { return handlers.size; },
    };
  }
  return {
    controller, publications, commands, warnings, runs, workspace, document, cancellation, emit,
    flush(delay) { for (const [id, timer] of timers) if (timer.delay === delay) { timers.delete(id); timer.fn(); } },
    dispose() { context.subscriptions.forEach((subscription) => subscription.dispose()); },
  };
}

test("a manual run cannot replace newer live diagnostics or the example tree", async () => {
  const h = await harness();
  const doc = h.document();
  const parent = h.controller.items.get(doc.uri.toString());
  const resolving = h.controller.resolveHandler(parent);
  await tick();
  h.commands[0].resolve(report("old"));
  await resolving;
  h.publications.length = 0;
  const running = h.controller.run({ include: [parent] }, h.cancellation());
  await tick();
  doc.version++;
  doc.text = "new";
  h.emit("change", { document: doc });
  h.flush(300);
  await tick();
  h.commands[2].resolve(report("new", "new diagnostic"));
  await tick();
  h.commands[1].resolve(report("old", "old diagnostic"));
  await running;
  assert.deepEqual(h.publications.map(({ problems }) => problems.map((item) => item.message)), [["new diagnostic"]]);
  assert.ok(parent.children.get(readReport(report("new"), "new").examples[0].id));
  assert.deepEqual(h.runs[0].results.map(([status, item]) => [status, item.label]), [["failed", "example item: old"]]);
  assert.ok(h.runs[0].ended);
  h.dispose();
});

test("running a file includes examples added since discovery", async () => {
  const h = await harness();
  const doc = h.document();
  const parent = h.controller.items.get(doc.uri.toString());
  const resolving = h.controller.resolveHandler(parent);
  await tick();
  h.commands[0].resolve(report("first"));
  await resolving;
  doc.version++;
  const running = h.controller.run({ include: [parent] }, h.cancellation());
  await tick();
  h.commands[1].resolve({ examples: [...report("first").examples, ...report("added").examples] });
  await running;
  assert.deepEqual(h.runs[0].results.map(([status, item]) => [status, item.label]), [
    ["passed", "example item: first"], ["passed", "example item: added"],
  ]);
  h.dispose();
});

test("resolve cannot publish after edits, file changes, or deletion", async () => {
  for (const event of ["edit", "fileChange", "delete"]) {
    const h = await harness();
    const doc = h.document();
    const parent = h.controller.items.get(doc.uri.toString());
    const resolving = h.controller.resolveHandler(parent);
    await tick();
    if (event === "edit") { doc.version++; h.emit("change", { document: doc }); }
    else h.emit(event, doc.uri);
    h.commands[0].resolve(report());
    await resolving;
    assert.equal(h.publications.length, 0, event);
    if (event === "delete") assert.equal(h.controller.items.size, 0);
    h.dispose();
  }
});

test("manual cancellation aborts its subprocess, ends the run, and does not warn", async () => {
  const h = await harness();
  const doc = h.document();
  const cancellation = h.cancellation();
  const running = h.controller.run({ include: [h.controller.items.get(doc.uri.toString())] }, cancellation);
  await tick();
  cancellation.cancel();
  await running;
  assert.equal(h.commands[0].signal.aborted, true);
  assert.equal(h.publications.length, 0);
  assert.deepEqual(h.warnings, []);
  assert.deepEqual(h.runs[0].results, []);
  assert.equal(h.runs[0].ended, true);
  assert.equal(cancellation.listeners, 0);
  h.dispose();
});

test("deactivation aborts manual and discovery checks without publishing after disposal", async () => {
  const h = await harness();
  const docs = [h.document("manual.names"), h.document("resolve.names")];
  const parents = docs.map((doc) => h.controller.items.get(doc.uri.toString()));
  const running = h.controller.run({ include: [parents[0]] }, h.cancellation());
  const resolving = h.controller.resolveHandler(parents[1]);
  await tick();
  assert.equal(h.commands.length, 2);
  h.dispose();
  await Promise.all([running, resolving]);
  assert.ok(h.commands.every(({ signal }) => signal.aborted));
  assert.equal(h.publications.length, 0);
  assert.deepEqual(h.warnings, []);
  assert.equal(h.runs[0].ended, true);
});

test("excluded examples never run as their parent or exclude an equal ID in another file", async () => {
  const h = await harness();
  const docs = [h.document("first.names"), h.document("second.names")];
  const parents = docs.map((doc) => h.controller.items.get(doc.uri.toString()));
  for (const parent of parents) {
    const resolving = h.controller.resolveHandler(parent);
    await tick();
    h.commands.at(-1).resolve(report());
    await resolving;
  }
  const id = readReport(report(), "x").examples[0].id;
  const running = h.controller.run({ include: parents, exclude: [parents[0].children.get(id)] }, h.cancellation());
  await tick();
  assert.equal(h.commands.length, 3);
  h.commands[2].resolve(report());
  await running;
  assert.deepEqual(h.runs[0].results.map(([status, item]) => [status, item.uri]), [["passed", docs[1].uri]]);
  h.dispose();
});
