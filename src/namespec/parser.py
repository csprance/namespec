"""Parse the rule language with a small hand-written parser. No third-party dependencies.

The language is deliberately tiny: identifiers, quoted strings, integers, six punctuation
characters and a dozen keywords. A tokenizer and a recursive-descent parser cover it in a
few hundred lines, report line and column on every error, and keep the runtime free of
parser libraries so a tool can ship the rule file itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .models import (
    SPEC_VERSION,
    Definition,
    ExampleSpec,
    FieldSpec,
    NameSpecError,
    ResourceSpec,
    check_root,
    fail,
    located,
    validate_field_spec,
)

Span = tuple[int, int]

TOKENS = re.compile(
    r"""
    (?P<space>[ \t\r\n]+)
  | (?P<comment>//[^\n]*)
  | (?P<id>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<int>-?[0-9]+)
  | (?P<string>"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')
  | (?P<punct>[{}\[\]=,])
    """,
    re.VERBOSE,
)
ESCAPES = {'"': '"', "'": "'", "\\": "\\"}
BLOCK_KEYWORDS = frozenset(
    {"spec", "resource", "example", "reject", "readers", "roots", "normalize"}
)
NORMALIZE_OPTIONS = {"slashes": ("forward",), "drive": ("upper", "lower")}


@dataclass(frozen=True)
class Token:
    kind: str
    value: Any
    start: int
    end: int
    line: int
    column: int

    def describe(self) -> str:
        if self.kind == "eof":
            return "end of file"
        if self.kind == "string":
            return "a string"
        return repr(self.value if self.kind != "int" else str(self.value))


def tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    position = 0
    line = 1
    line_start = 0
    while position < len(source):
        match = TOKENS.match(source, position)
        if match is None:
            character = source[position]
            what = "unterminated string" if character in "\"'" else f"unexpected {character!r}"
            fail("syntax_error", f"{what}.", span=(position, position + 1))
        kind = match.lastgroup
        text = match.group()
        if kind == "id":
            value: Any = text
        elif kind == "int":
            value = int(text)
        elif kind == "string":
            value = unescape(text[1:-1])
        else:
            value = text
        if kind not in {"space", "comment"}:
            tokens.append(
                Token(kind, value, position, match.end(), line, position - line_start + 1)
            )
        newlines = text.count("\n")
        if newlines:
            line += newlines
            line_start = position + text.rfind("\n") + 1
        position = match.end()
    tokens.append(Token("eof", None, len(source), len(source), line, len(source) - line_start + 1))
    return tokens


def unescape(body: str) -> str:
    """Backslash escapes the quote characters and itself; anything else is kept verbatim.

    Regex patterns such as "\\d+" therefore survive untouched inside a rule document.
    """
    out: list[str] = []
    index = 0
    while index < len(body):
        character = body[index]
        if character == "\\" and index + 1 < len(body):
            following = body[index + 1]
            if following in ESCAPES:
                out.append(ESCAPES[following])
                index += 2
                continue
        out.append(character)
        index += 1
    return "".join(out)


class Parser:
    def __init__(self, source: str):
        self.tokens = tokenize(source)
        self.position = 0
        self.fields: dict[str, FieldSpec] = {}
        self.resources: dict[str, ResourceSpec] = {}
        self.readers: dict[str, str] = {}
        self.roots: dict[str, str] = {}
        self.normalize: dict[str, str] = {}
        self.examples: list[ExampleSpec] = []
        self.spans: dict[tuple[str | int, ...], Span] = {}

    # Token helpers -----------------------------------------------------------------------

    def peek(self, ahead: int = 0) -> Token:
        return self.tokens[min(self.position + ahead, len(self.tokens) - 1)]

    def advance(self) -> Token:
        token = self.peek()
        if token.kind != "eof":
            self.position += 1
        return token

    def since(self, token: Token) -> Span:
        """From the start of ``token`` to the end of the last token read."""
        return token.start, self.tokens[self.position - 1].end

    def error(self, expected: str, token: Token | None = None) -> None:
        token = token or self.peek()
        fail(
            "syntax_error",
            f"expected {expected}, found {token.describe()}.",
            span=(token.start, token.end),
        )

    def accept(self, kind: str, value: Any = None) -> Token | None:
        token = self.peek()
        if token.kind == kind and (value is None or token.value == value):
            return self.advance()
        return None

    def expect(self, kind: str, value: Any = None, expected: str | None = None) -> Token:
        token = self.accept(kind, value)
        if token is None:
            self.error(expected or (repr(value) if value is not None else kind))
        return token

    def keyword(self, word: str) -> Token:
        return self.expect("id", word, repr(word))

    def punct(self, mark: str) -> Token:
        return self.expect("punct", mark, repr(mark))

    def string(self, what: str = "a string") -> str:
        return self.expect("string", expected=what).value

    def identifier(self, what: str = "a name") -> str:
        return self.expect("id", expected=what).value

    def strings(self) -> list[Token]:
        tokens = [self.expect("string", expected="a string")]
        while self.accept("punct", ","):
            tokens.append(self.expect("string", expected="a string"))
        return tokens

    def value(self) -> str | int:
        token = self.peek()
        if token.kind in {"string", "int"}:
            return self.advance().value
        self.error("a string or an integer")

    # Grammar ------------------------------------------------------------------------------

    def parse(self) -> Definition:
        self.keyword("spec")
        version_token = self.expect("int", expected="a specification version")
        if version_token.value != SPEC_VERSION:
            fail(
                "unsupported_spec",
                f"Unsupported specification version: {version_token.value}.",
                span=(version_token.start, version_token.end),
            )
        while self.peek().kind != "eof":
            self.declaration()
        if not self.resources:
            fail("missing_resource", "Define at least one resource.")
        for index, example in enumerate(self.examples):
            if example.resource not in self.resources:
                fail(
                    "unknown_resource",
                    f"Example references unknown resource {example.resource!r}.",
                    span=self.spans[("example", index, "resource")],
                )
        return Definition(
            version_token.value,
            self.fields,
            self.resources,
            self.readers,
            tuple(self.examples),
            self.roots,
            self.normalize,
            self.spans,
        )

    def declaration(self) -> None:
        token = self.peek()
        following = self.peek(1)
        if token.kind != "id":
            self.error("a declaration")
        if token.value == "resource" and following.kind == "id":
            self.resource()
        elif token.value in {"example", "reject"} and following.kind == "id":
            self.example(token.value == "reject")
        elif token.value in {"readers", "roots", "normalize"} and following.value == "{":
            self.block(token.value)
        elif following.value == "=":
            self.field()
        else:
            self.error("a declaration")

    def field(self) -> None:
        name_token = self.advance()
        name = name_token.value
        if name in BLOCK_KEYWORDS or name == "meta":
            fail(
                "reserved_field",
                f"{name!r} is a keyword and cannot name a field.",
                span=(name_token.start, name_token.end),
            )
        self.punct("=")
        token = self.peek()
        samples: list[Token] = []
        if token.kind == "string":
            spec = FieldSpec(name, "composite", template=self.advance().value)
        elif self.accept("id", "text"):
            self.keyword("matching")
            pattern = self.string("a pattern")
            samples = self.strings() if self.accept("id", "examples") else []
            spec = FieldSpec(
                name, "text", pattern=pattern, samples=tuple(item.value for item in samples)
            )
        elif self.accept("id", "integer"):
            self.keyword("minimum")
            minimum = self.expect("int", expected="a minimum").value
            width = 0
            if self.accept("id", "padded"):
                self.keyword("to")
                width = self.expect("int", expected="a digit count").value
                self.keyword("digits")
            spec = FieldSpec(name, "integer", minimum=minimum, width=width)
        elif self.accept("id", "one"):
            self.keyword("of")
            spec = FieldSpec(name, "enum", choices=tuple(item.value for item in self.strings()))
        else:
            self.error(
                'a field rule: text matching "...", integer minimum N, one of "...", or a template'
            )
        span = self.since(name_token)
        with located(span):
            validate_field_spec(spec, [(item.start, item.end) for item in samples])
        insert(self.fields, name, spec, (name_token.start, name_token.end))
        self.spans[("field", name)] = span

    def resource(self) -> None:
        self.keyword("resource")
        name_token = self.expect("id", expected="a resource name")
        name = name_token.value
        self.punct("{")
        entries: dict[str, Any] = {}
        metadata: dict[str, Any] = {}
        while not self.accept("punct", "}"):
            key_token = self.peek()
            if key_token.kind != "id":
                self.error("name, location, reader, meta or '}'")
            key = key_token.value
            if key in entries or (key == "meta" and metadata):
                fail(
                    "duplicate_definition",
                    f"Resource {name!r} repeats {key!r}.",
                    span=(key_token.start, key_token.end),
                )
            self.advance()
            if key in {"name", "location"}:
                self.punct("=")
                entries[key] = self.string("a template")
            elif key == "reader":
                self.punct("=")
                self.keyword("readers")
                self.punct("[")
                entries[key] = self.identifier("a field name")
                self.punct("]")
            elif key == "meta":
                self.punct("{")
                while not self.accept("punct", "}"):
                    meta_token = self.expect("id", expected="a metadata key or '}'")
                    self.punct("=")
                    if self.accept("punct", "["):
                        items: list[str | int] = []
                        if not self.accept("punct", "]"):
                            items.append(self.value())
                            while self.accept("punct", ","):
                                items.append(self.value())
                            self.punct("]")
                        value: Any = tuple(items)
                    else:
                        value = self.value()
                    insert(metadata, meta_token.value, value, self.since(meta_token))
                entries["meta"] = True
            else:
                self.error("name, location, reader, meta or '}'", key_token)
            self.spans[("resource", name, key)] = self.since(key_token)
        name_span = (name_token.start, name_token.end)
        if "name" not in entries and "location" not in entries:
            fail(
                "invalid_resource",
                f"Resource {name!r} needs a name or a location.",
                span=name_span,
            )
        insert(
            self.resources,
            name,
            ResourceSpec(
                name,
                entries.get("name"),
                entries.get("location"),
                entries.get("reader"),
                metadata,
            ),
            name_span,
        )
        self.spans[("resource", name)] = name_span

    def block(self, kind: str) -> None:
        self.advance()
        self.punct("{")
        target = {"readers": self.readers, "roots": self.roots, "normalize": self.normalize}[kind]
        while not self.accept("punct", "}"):
            key_token = self.peek()
            key = self.identifier("an entry name or '}'")
            self.punct("=")
            value = self.string()
            span = self.since(key_token)
            if kind == "readers":
                if not value:
                    fail("empty_handler", "Reader handler IDs cannot be empty.", span=span)
            elif kind == "roots":
                with located(span):
                    check_root(key, value)
                if value in self.roots.values():
                    fail("duplicate_root", f"Root {key!r} repeats another root's path.", span=span)
            else:
                allowed = NORMALIZE_OPTIONS.get(key)
                if allowed is None or value not in allowed:
                    fail(
                        "invalid_normalize",
                        "Normalize accepts "
                        + ", ".join(
                            f"{k} = {' | '.join(map(repr, v))}"
                            for k, v in NORMALIZE_OPTIONS.items()
                        )
                        + ".",
                        span=(key_token.start, key_token.end),
                    )
            insert(target, key, value, span)

    def example(self, rejection: bool) -> None:
        key = ("example", len(self.examples))
        keyword = self.advance()
        resource_token = self.expect("id", expected="a resource name")
        self.spans[(*key, "resource")] = (resource_token.start, resource_token.end)
        self.punct("{")
        source_token = self.peek()
        if self.accept("id", "input"):
            source = "name"
        elif self.accept("id", "location"):
            source = "location"
        else:
            self.error("input or location", source_token)
        self.punct("=")
        text_token = self.expect("string", expected="a string")
        self.spans[(*key, "input")] = (text_token.start, text_token.end)
        self.keyword("expect")
        expected: dict[str, str | int] = {}
        code = None
        if rejection:
            self.punct("=")
            code_token = self.expect("string", expected="a diagnostic code")
            code = code_token.value
            self.spans[(*key, "expect")] = (code_token.start, code_token.end)
        else:
            opening = self.punct("{")
            while not self.accept("punct", "}"):
                field_token = self.expect("id", expected="a field name or '}'")
                self.punct("=")
                value = self.value()
                span = self.since(field_token)
                insert(expected, field_token.value, value, span)
                self.spans[(*key, "expect", field_token.value)] = span
            self.spans[(*key, "expect")] = self.since(opening)
        self.punct("}")
        self.spans[key] = self.since(keyword)
        self.examples.append(
            ExampleSpec(resource_token.value, text_token.value, expected, code, source)
        )


def insert(target: dict, name: str, value: object, span: Span | None = None) -> None:
    if name in target:
        fail("duplicate_definition", f"Duplicate definition: {name!r}.", span=span)
    target[name] = value


def compile_definition(source: str) -> Definition:
    """Parse rule text into a Definition. Errors raise NameSpecError with a source span."""
    try:
        return Parser(source).parse()
    except NameSpecError as exc:
        raise NameSpecError(exc.diagnostics, source) from None
