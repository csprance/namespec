const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { before, test } = require("node:test");
const { loadGrammar } = require("../grammar.cjs");
const { indexDefinitions } = require("../definitions.cjs");

let grammar;
before(async () => { grammar = await loadGrammar(); });

function targets(source, reference, inside = 0) {
  const offset = source.indexOf(reference) + inside;
  assert.ok(offset >= inside, reference);
  return indexDefinitions(source, grammar)(offset).map(({ target }) => target.start);
}

test("template fields resolve forward and backward with exact UTF-16/CRLF positions", () => {
  const source = '// 🪁 notes\r\nasset = text matching "[A-Z]+"\r\n' +
    'resource model { name = "{asset}_v{version}" }\r\nversion\r\n = integer minimum 1';
  assert.deepEqual(targets(source, "{asset}", 2), [source.indexOf("asset =")]);
  assert.deepEqual(targets(source, "{version}", 3), [source.indexOf("version\r")]);
});

test("name placeholders resolve to the owning resource's name assignment", () => {
  const source = 'item = text matching "[a-z]+"\n' +
    'resource first { name = "{item}.abc" location = "/a/{name}" }\n' +
    'resource second { name = "{item}.usd" location = "/b/{name}" }';
  assert.deepEqual(targets(source, '/a/{name}', 5), [source.indexOf('name = "{item}.abc"')]);
  assert.deepEqual(targets(source, '/b/{name}', 5), [source.indexOf('name = "{item}.usd"')]);
});

test("example and reject resource references use a separate namespace from fields", () => {
  const source = 'example asset { input = "A" expect { asset = "A" } }\n' +
    'reject asset { input = "?" expect = "invalid_field" }\n' +
    'asset = text matching "[A-Z]+"\nresource asset { name = "{asset}" }';
  const resource = source.indexOf('asset { name');
  assert.deepEqual(targets(source, "example asset", 9), [resource]);
  assert.deepEqual(targets(source, "reject asset", 8), [resource]);
  assert.deepEqual(targets(source, 'asset = "A"'), [source.indexOf('asset = text')]);
});

test("reader references link to every mapping block and to the selected field", () => {
  const source = 'ext = one of "abc", "usd"\n' +
    'resource item { name = "{ext}" reader = readers[ext] }\n' +
    'readers { abc = "alembic" }\nreaders { usd = "usd" }';
  assert.deepEqual(targets(source, 'readers[ext]', 2), [source.indexOf('readers { abc'), source.indexOf('readers { usd')]);
  assert.deepEqual(targets(source, 'readers[ext]', 9), [0]);
});

test("comments, string values, regexes and escaped braces do not create links or declarations", () => {
  const source = String.raw`// bogus = text matching "x" resource fake { name = "{field}" }
field = text matching "[a-z]{2}" examples "resource fake"
resource item { name = 'prefix\'{field}_{{literal}}_{missing}' }
example item { input = "literal_{field}" expect { field = "{field}" } }`;
  assert.deepEqual(targets(source, "{field}", 2), []);
  assert.deepEqual(targets(source, "{2}", 1), []);
  assert.deepEqual(targets(source, "{{literal}}", 3), []);
  assert.deepEqual(targets(source, "{missing}", 2), []);
  assert.deepEqual(targets(source, "literal_{field}", 10), []);
  assert.deepEqual(targets(source, 'field = "{field}"', 12), []);
  assert.deepEqual(targets(source, "prefix\\'{field}", 10), [source.indexOf("field = text")]);
});

test("multiple declarations are returned instead of silently choosing one", () => {
  const source = 'item = one of "a"\nitem = one of "b"\nresource data { name = "{item}" }';
  assert.deepEqual(targets(source, '{item}', 2), [0, source.indexOf('item = one of "b"')]);
});

test("navigation survives an unfinished resource and ignores unrelated words", () => {
  const source = 'item = one of "a"\nresource data { name = "{item}_{unknown}"';
  assert.deepEqual(targets(source, '{item}', 2), [0]);
  assert.deepEqual(targets(source, '{unknown}', 2), []);
  assert.deepEqual(targets(source, 'resource'), []);
});

test("every placeholder in both shipped examples has a declaration", () => {
  for (const filename of ["assets.names", "studio.names"]) {
    const source = fs.readFileSync(path.join(__dirname, "../../../examples", filename), "utf8");
    const lookup = indexDefinitions(source, grammar);
    for (const line of source.matchAll(/^\s*(?:name|location)\s*=.*$/gm)) {
      for (const slot of line[0].matchAll(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g)) {
        const links = lookup(line.index + slot.index + 1);
        assert.equal(links.length, 1, `${filename}: ${slot[0]}`);
        assert.equal(source.slice(links[0].target.start, links[0].target.end), slot[1]);
      }
    }
  }
});

test("preview ranges contain multiline values without neighboring declarations or comments", () => {
  const declaration = 'role = text matching "[a-z]+"\r\n    examples "main", "detail"';
  const source = declaration + '\r\n// next field\r\next = one of "abc"\r\n' +
    'resource item { name = "{role}.{ext}" }';
  for (const offset of [1, source.indexOf('{role}') + 2]) {
    const [{ target }] = indexDefinitions(source, grammar)(offset);
    assert.equal(source.slice(target.rangeStart ?? target.start, target.rangeEnd), declaration);
  }
  const enumTarget = indexDefinitions(source, grammar)(source.indexOf('{ext}') + 2)[0].target;
  assert.equal(source.slice(enumTarget.start, enumTarget.rangeEnd), 'ext = one of "abc"');
});

test("resource, reader and built-in name previews have distinct complete ranges", () => {
  const resource = 'resource model {\n name = "{asset}"\n location = "/{name}"\n reader = readers[ext]\n}';
  const readers = 'readers {\n abc = "alembic"\n}';
  const source = 'asset = text matching "[a-z]+"\next = one of "abc"\n' + resource + '\n' + readers +
    '\nexample model { input = "chair" expect { asset = "chair" } }';
  const preview = (offset) => {
    const { target } = indexDefinitions(source, grammar)(offset)[0];
    return source.slice(target.rangeStart ?? target.start, target.rangeEnd);
  };
  assert.equal(preview(source.indexOf('example model') + 9), resource);
  assert.equal(preview(source.indexOf('readers[ext]') + 2), readers);
  assert.equal(preview(source.indexOf('{name}') + 2), 'name = "{asset}"');
});

test("preview includes final numeric constraints and tolerates incomplete blocks", () => {
  const source = 'resource item { name = "{version}" }\nversion = integer minimum 1 padded to 3 digits\n// trailing note';
  const { target } = indexDefinitions(source, grammar)(source.indexOf('{version}') + 2)[0];
  assert.equal(source.slice(target.start, target.rangeEnd), 'version = integer minimum 1 padded to 3 digits');
  const unfinished = 'example model { input = "x" }\nresource model { name = "{unknown}"';
  const partial = indexDefinitions(unfinished, grammar)(unfinished.indexOf('model') + 1)[0].target;
  assert.equal(unfinished.slice(partial.rangeStart, partial.rangeEnd), 'resource model { name = "{unknown}"');
});
