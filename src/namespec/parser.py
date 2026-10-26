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
    ResourceSpec,
    check_root,
    fail,
    validate_field_spec,
)

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
            fail(
                "syntax_error",
                f"line {line}, column {position - line_start + 1}: {what}.",
                span=(position, position + 1),
            )
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

    # Token helpers -----------------------------------------------------------------------

    def peek(self, ahead: int = 0) -> Token:
        return self.tokens[min(self.position + ahead, len(self.tokens) - 1)]

    def advance(self) -> Token:
        token = self.peek()
        if token.kind != "eof":
            self.position += 1
        return token

    def error(self, expected: str, token: Token | None = None) -> None:
        token = token or self.peek()
        fail(
            "syntax_error",
            f"line {token.line}, column {token.column}: expected {expected}, "
            f"found {token.describe()}.",
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

    def strings(self) -> list[str]:
        values = [self.string()]
        while self.accept("punct", ","):
            values.append(self.string())
        return values

    def value(self) -> str | int:
        token = self.peek()
        if token.kind in {"string", "int"}:
            return self.advance().value
        self.error("a string or an integer")

    # Grammar ------------------------------------------------------------------------------

    def parse(self) -> Definition:
        self.keyword("spec")
        version = self.expect("int", expected="a specification version").value
        if version != SPEC_VERSION:
            fail("unsupported_spec", f"Unsupported specification version: {version}.")
        while self.peek().kind != "eof":
            self.declaration()
        if not self.resources:
            fail("missing_resource", "Define at least one resource.")
        for example in self.examples:
            if example.resource not in self.resources:
                fail(
                    "unknown_resource",
                    f"Example references unknown resource {example.resource!r}.",
                )
        return Definition(
            version,
            self.fields,
            self.resources,
            self.readers,
            tuple(self.examples),
            self.roots,
            self.normalize,
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
                f"line {name_token.line}: {name!r} is a keyword and cannot name a field.",
                span=(name_token.start, name_token.end),
            )
        self.punct("=")
        token = self.peek()
        if token.kind == "string":
            spec = FieldSpec(name, "composite", template=self.advance().value)
        elif self.accept("id", "text"):
            self.keyword("matching")
            pattern = self.string("a pattern")
            samples = self.strings() if self.accept("id", "examples") else []
            spec = FieldSpec(name, "text", pattern=pattern, samples=tuple(samples))
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
            spec = FieldSpec(name, "enum", choices=tuple(self.strings()))
        else:
            self.error(
                'a field rule: text matching "...", integer minimum N, one of "...", or a template'
            )
        validate_field_spec(spec)
        insert(self.fields, name, spec)

    def resource(self) -> None:
        self.keyword("resource")
        name = self.identifier("a resource name")
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
                    f"line {key_token.line}: resource {name!r} repeats {key!r}.",
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
                    meta_key = self.identifier("a metadata key or '}'")
                    self.punct("=")
                    if self.accept("punct", "["):
                        items: list[str | int] = []
                        if not self.accept("punct", "]"):
                            items.append(self.value())
                            while self.accept("punct", ","):
                                items.append(self.value())
                            self.punct("]")
                        insert(metadata, meta_key, tuple(items))
                    else:
                        insert(metadata, meta_key, self.value())
                entries["meta"] = True
            else:
                self.error("name, location, reader, meta or '}'", key_token)
        if "name" not in entries and "location" not in entries:
            fail("invalid_resource", f"Resource {name!r} needs a name or a location.")
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
        )

    def block(self, kind: str) -> None:
        self.advance()
        self.punct("{")
        target = {"readers": self.readers, "roots": self.roots, "normalize": self.normalize}[kind]
        while not self.accept("punct", "}"):
            key_token = self.peek()
            key = self.identifier("an entry name or '}'")
            self.punct("=")
            value = self.string()
            if kind == "readers":
                if not value:
                    fail("empty_handler", "Reader handler IDs cannot be empty.")
            elif kind == "roots":
                check_root(key, value)
                if value in self.roots.values():
                    fail("duplicate_root", f"Root {key!r} repeats another root's path.")
            else:
                allowed = NORMALIZE_OPTIONS.get(key)
                if allowed is None or value not in allowed:
                    fail(
                        "invalid_normalize",
                        f"line {key_token.line}: normalize accepts "
                        + ", ".join(
                            f"{k} = {' | '.join(map(repr, v))}"
                            for k, v in NORMALIZE_OPTIONS.items()
                        )
                        + ".",
                        span=(key_token.start, key_token.end),
                    )
            insert(target, key, value)

    def example(self, rejection: bool) -> None:
        self.advance()
        resource = self.identifier("a resource name")
        self.punct("{")
        source_token = self.peek()
        if self.accept("id", "input"):
            source = "name"
        elif self.accept("id", "location"):
            source = "location"
        else:
            self.error("input or location", source_token)
        self.punct("=")
        text = self.string()
        self.keyword("expect")
        expected: dict[str, str | int] = {}
        code = None
        if rejection:
            self.punct("=")
            code = self.string("a diagnostic code")
        else:
            self.punct("{")
            while not self.accept("punct", "}"):
                key = self.identifier("a field name or '}'")
                self.punct("=")
                insert(expected, key, self.value())
        self.punct("}")
        self.examples.append(ExampleSpec(resource, text, expected, code, source))


def insert(target: dict, name: str, value: object) -> None:
    if name in target:
        fail("duplicate_definition", f"Duplicate definition: {name!r}.")
    target[name] = value


def compile_definition(source: str) -> Definition:
    """Parse rule text into a Definition. Errors raise NameSpecError with a source span."""
    return Parser(source).parse()
