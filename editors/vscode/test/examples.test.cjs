const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const { VENV, findCommand, readReport, runExamples } = require("../examples.cjs");

const ROOT = path.join(__dirname, "../../..");
const CLI = path.join(ROOT, ...VENV);
const GUIDE = fs.readFileSync(path.join(ROOT, "examples/guide.names"), "utf8");

test("the command is the setting, else the nearest .venv above the rules, else PATH", () => {
  const rules = path.join("D:", "jobs", "show", "rules");
  const venv = path.join("D:", "jobs", ...VENV);
  assert.equal(findCommand(rules, "C:/tools/namespec.exe", () => true), "C:/tools/namespec.exe");
  assert.equal(findCommand(rules, "", (candidate) => candidate === venv), venv);
  assert.equal(findCommand(rules, "", () => false), "namespec");
  assert.equal(findCommand(undefined, undefined, () => true), "namespec");
});

test("code point spans become UTF-16 positions in CRLF text", () => {
  const text = "// 🪁 kite\r\nspec 1\r\nexample a { input = \"x\" }";
  // Python counts the kite as one character, VS Code as two units.
  const start = Array.from(text.slice(0, text.indexOf('"x"'))).length;
  const failure = { code: "example_failed", message: "Nope.", span: [start, start + 3] };
  const { problems } = readReport({
    examples: [{ kind: "example", resource: "a", input: "x", passed: false, span: [0, 1], failures: [failure] }],
  }, text);
  assert.deepEqual(problems, [{
    code: "example_failed",
    message: "Nope.",
    range: { start: { line: 2, character: 20 }, end: { line: 2, character: 23 } },
  }]);
});

test("unloadable rules keep their problems and report no examples", () => {
  const report = readReport({ diagnostics: [{ code: "missing_resource", message: "Define at least one resource.", span: null }] }, "spec 1\r\n");
  assert.equal(report.loaded, false);
  assert.deepEqual(report.problems[0].range, { start: { line: 0, character: 0 }, end: { line: 0, character: 6 } });
});

test("repeated examples get distinct, stable ids", () => {
  const example = { kind: "reject", resource: "model", input: "x", passed: true, span: [0, 1], failures: [] };
  const { examples } = readReport({ examples: [example, example] }, "x");
  assert.deepEqual(examples.map((item) => item.id), ["reject model: x", "reject model: x (2)"]);
});

const live = fs.existsSync(CLI) ? test : test.skip;

live("the Python command checks an unsaved buffer and points at the wrong field", async () => {
  const passing = readReport(await runExamples(CLI, GUIDE), GUIDE);
  assert.equal(passing.loaded, true);
  assert.equal(passing.problems.length, 0);
  assert.ok(passing.examples.length >= 9 && passing.examples.every((example) => example.passed));
  const first = passing.examples[0];
  assert.equal(first.label, "example model: Donut_high_v004.abc");
  assert.match(GUIDE.split("\n")[first.range.start.line], /^example model \{\r?$/);

  const broken = GUIDE.replace(/\n/g, "\r\n").replace('lod = "high" version = 4', 'lod = "mid" version = 4');
  const failing = readReport(await runExamples(CLI, broken), broken);
  assert.deepEqual(failing.problems.map((problem) => problem.message), ['Expected lod = "mid", got "high".']);
  const { start, end } = failing.problems[0].range;
  assert.equal(broken.split("\r\n")[start.line].slice(start.character, end.character), 'lod = "mid"');
  assert.equal(failing.examples.filter((example) => !example.passed).length, 1);

  const unloadable = broken.replace("{lod}", "{lodd}");
  const error = readReport(await runExamples(CLI, unloadable), unloadable);
  assert.equal(error.loaded, false);
  assert.equal(error.problems[0].code, "unknown_field");
  assert.match(unloadable.split("\r\n")[error.problems[0].range.start.line], /^\s+name\s+= "\{asset\}_\{lodd\}/);
});

test("a missing command rejects with ENOENT so the editor can say so", async () => {
  await assert.rejects(runExamples("namespec-not-installed-anywhere", "spec 1"), { code: "ENOENT" });
});
