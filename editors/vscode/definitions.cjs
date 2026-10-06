const { INITIAL } = require("vscode-textmate");

// Reuse the highlighting grammar to exclude comments, literal strings and escaped
// braces. Offsets stay in JavaScript/VS Code UTF-16 units, including CRLF files.
function tokensFor(source, grammar) {
  const tokens = [];
  let state = INITIAL;
  let offset = 0;
  for (const line of source.split("\n")) {
    const result = grammar.tokenizeLine(line, state);
    state = result.ruleStack;
    for (const token of result.tokens) {
      const slot = token.scopes.includes("variable.parameter.namespec");
      if (token.scopes.some((scope) => scope.startsWith("comment"))) continue;
      const text = line.slice(token.startIndex, token.endIndex);
      // Keep opaque string spans for complete declaration previews, but never
      // interpret their contents as declarations or block delimiters.
      if (!slot && token.scopes.some((scope) => /^(string|constant.character|punctuation.definition.string)/.test(scope))) {
        tokens.push({ text, start: offset + token.startIndex, end: offset + token.startIndex + text.length, literal: true });
        continue;
      }
      for (const match of text.matchAll(/[A-Za-z_][A-Za-z0-9_]*|-?[0-9]+|[{}\[\]=,]/g)) {
        const start = offset + token.startIndex + match.index;
        tokens.push({ text: match[0], start, end: start + match[0].length, slot });
      }
    }
    offset += line.length + 1;
  }
  return tokens;
}

function indexDefinitions(source, grammar) {
  const tokens = tokensFor(source, grammar);
  const declarations = new Map();
  const references = [];
  const stack = [];
  let pending;
  let field;
  const declare = (key, token) => {
    const targets = declarations.get(key) ?? [];
    targets.push(token);
    declarations.set(key, targets);
  };
  const refer = (token, key, owner) => references.push({ token, key, owner });
  const finishField = (end) => {
    if (field) field.rangeEnd = end;
    field = undefined;
  };
  const finishTemplate = (context, end) => {
    if (context?.template && context.template.rangeEnd === undefined) context.template.rangeEnd = end;
  };

  // Only index declaration/reference sites; validation remains the Python
  // package's job. Keeping block context also tolerates a file being edited.
  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i];
    const next = tokens[i + 1];
    const after = tokens[i + 2];
    const context = stack.at(-1);
    if (token.literal) continue;
    if (token.slot) {
      if (context?.kind === "resource") {
        refer(token, `field:${token.text}`, token.text === "name" ? context : undefined);
      }
      continue;
    }
    if (token.text === "{") {
      stack.push(pending ?? { kind: "unknown" });
      pending = undefined;
      continue;
    }
    if (token.text === "}") {
      if (context?.target) context.target.rangeEnd = token.end;
      finishTemplate(context, tokens[i - 1]?.end ?? token.start);
      stack.pop();
      pending = undefined;
      continue;
    }
    if (!context) {
      if (["resource", "example", "reject"].includes(token.text) && after?.text === "{") {
        finishField(tokens[i - 1]?.end ?? token.start);
        if (token.text === "resource") {
          next.rangeStart = token.start;
          declare(`resource:${next.text}`, next);
        }
        refer(next, `resource:${next.text}`);
        pending = { kind: token.text, target: token.text === "resource" ? next : undefined };
        i++;
      } else if (token.text === "readers" && next?.text === "{") {
        finishField(tokens[i - 1]?.end ?? token.start);
        declare("readers", token);
        refer(token, "readers");
        pending = { kind: "readers", target: token };
      } else if (next?.text === "=" && ["text", "integer", "one"].includes(after?.text)) {
        finishField(tokens[i - 1]?.end ?? token.start);
        field = token;
        declare(`field:${token.text}`, token);
        refer(token, `field:${token.text}`);
      }
    } else if (context.kind === "resource") {
      if (["name", "location", "reader"].includes(token.text) && next?.text === "=") {
        finishTemplate(context, tokens[i - 1]?.end ?? token.start);
        if (token.text === "name") {
          context.template = token;
          refer(token, "", context);
        }
      }
      if (token.text === "readers" && next?.text === "[") {
        refer(token, "readers");
        if (after && after.text !== "]") refer(after, `field:${after.text}`);
      }
    } else if (context.kind === "example" && token.text === "expect" && next?.text === "{") {
      pending = { kind: "expect" };
    } else if (context.kind === "expect" && next?.text === "=") {
      refer(token, `field:${token.text}`);
    }
  }
  finishField(tokens.at(-1)?.end ?? source.length);
  for (const context of stack) {
    if (context.target) context.target.rangeEnd = source.length;
    finishTemplate(context, source.length);
  }

  return (offset) => {
    const reference = references.find(({ token }) => token.start <= offset && offset < token.end);
    if (!reference) return [];
    const targets = reference.owner
      ? [reference.owner.template].filter(Boolean)
      : declarations.get(reference.key) ?? [];
    return targets.map((target) => ({ origin: reference.token, target }));
  };
}

module.exports = { indexDefinitions };
