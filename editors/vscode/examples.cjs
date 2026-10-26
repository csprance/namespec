const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

// Checking runs the Python package, so the editor and `namespec rules.names test` always
// agree. The command reads the unsaved buffer on stdin and reports Python string offsets,
// which count code points; editors count UTF-16 units.

const VENV = process.platform === "win32"
  ? [".venv", "Scripts", "namespec.exe"]
  : [".venv", "bin", "namespec"];

// The configured command, else the nearest .venv at or above the rules, else PATH.
function findCommand(directory, configured, exists = fs.existsSync) {
  if (configured) return configured;
  for (let folder = directory; folder; folder = path.dirname(folder)) {
    const candidate = path.join(folder, ...VENV);
    if (exists(candidate)) return candidate;
    if (path.dirname(folder) === folder) break;
  }
  return "namespec";
}

function runExamples(command, text, { cwd, signal, timeout = 15000 } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, ["-", "test", "--json"], { cwd, signal, windowsHide: true });
    // spawn's own timeout option leaves its timer running when the command is missing.
    const timer = setTimeout(() => child.kill(), timeout);
    const stdout = [];
    const stderr = [];
    child.stdout.on("data", (chunk) => stdout.push(chunk));
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    // The process may exit before reading all of stdin; its output still explains why.
    child.stdin.on("error", () => {});
    child.on("close", (code) => {
      clearTimeout(timer);
      const output = Buffer.concat(stdout).toString("utf8");
      try {
        resolve(JSON.parse(output));
      } catch {
        const detail = Buffer.concat(stderr).toString("utf8").trim() || output.trim();
        reject(new Error(`${command} exited with ${code}${detail ? `: ${detail}` : ""}`));
      }
    });
    child.stdin.end(text, "utf8");
  });
}

function utf16(text) {
  if (!/[\uD800-\uDBFF]/.test(text)) return (offset) => offset;
  const units = [0];
  for (const character of text) units.push(units[units.length - 1] + character.length);
  return (offset) => units[Math.min(offset, units.length - 1)];
}

// Turns a [start, end] code point span into zero-based line/character positions. A
// diagnostic without a span is about the whole file and lands on the first line.
function locator(text) {
  const units = utf16(text);
  const starts = [0];
  for (let i = text.indexOf("\n"); i !== -1; i = text.indexOf("\n", i + 1)) starts.push(i + 1);
  const at = (offset) => {
    let low = 0;
    let high = starts.length - 1;
    while (low < high) {
      const middle = (low + high + 1) >> 1;
      if (starts[middle] <= offset) low = middle;
      else high = middle - 1;
    }
    return { line: low, character: offset - starts[low] };
  };
  const firstLine = text.split("\n", 1)[0].replace(/\r$/, "").length;
  return (span) => span
    ? { start: at(units(span[0])), end: at(units(span[1])) }
    : { start: { line: 0, character: 0 }, end: { line: 0, character: firstLine } };
}

// The editor's view of a `test --json` report: problems to underline and, when the rules
// loaded, one entry per example. Ids stay stable while lines above an example change.
function readReport(report, text) {
  const where = locator(text);
  const problem = (item) => ({ code: item.code, message: item.message, range: where(item.span) });
  if (!Array.isArray(report.examples)) {
    const problems = (report.diagnostics ?? [{ code: "error", message: report.error }]).map(problem);
    return { loaded: false, problems, examples: [] };
  }
  const seen = new Map();
  const examples = report.examples.map((example) => {
    const label = `${example.kind} ${example.resource}: ${example.input}`;
    const count = (seen.get(label) ?? 0) + 1;
    seen.set(label, count);
    return {
      id: count > 1 ? `${label} (${count})` : label,
      label,
      range: where(example.span),
      passed: example.passed,
      failures: example.failures.map(problem),
    };
  });
  return { loaded: true, problems: examples.flatMap((example) => example.failures), examples };
}

module.exports = { VENV, findCommand, readReport, runExamples };
