"""The hand-written parser: positions on errors, string escapes, and declaration shapes."""

from __future__ import annotations

import pytest

from namespec import Catalog, NameSpecError
from namespec.parser import tokenize, unescape


def diagnostics(source):
    with pytest.raises(NameSpecError) as exc:
        Catalog.from_string(source)
    return exc.value.diagnostics


def error(source):
    with pytest.raises(NameSpecError) as exc:
        Catalog.from_string(source)
    return str(exc.value)


def test_syntax_errors_carry_line_column_and_span():
    source = 'spec 1\nx = one of "a"\nresource r { name = "{x}" '
    [item] = diagnostics(source)
    assert item.code == "syntax_error"
    assert "found end of file" in item.message
    assert item.span == (len(source), len(source))
    assert error(source).startswith("line 3, column 27: expected")
    [item] = diagnostics('spec 1\n  x = one of "a')
    assert item.message == "unterminated string."
    assert item.span == (20, 21)
    assert error('spec 1\n  x = one of "a') == "line 2, column 14: unterminated string."
    [item] = diagnostics("spec 1\nx = one of @")
    assert "unexpected '@'" in item.message
    [item] = diagnostics('spec 1 resource r { name = "{x}" input = "y" }')
    assert "expected name, location, reader, meta or '}', found 'input'" in item.message
    [item] = diagnostics("spec 1 x = integer minimum 1 padded to three digits")
    assert "expected a digit count, found 'three'" in item.message
    [item] = diagnostics('spec 1 example r { expect { } input = "a" }')
    assert "expected input or location, found 'expect'" in item.message
    [item] = diagnostics("")
    assert "expected 'spec', found end of file" in item.message
    [item] = diagnostics('spec 1 "stray"')
    assert "expected a declaration, found a string" in item.message
    [item] = diagnostics("spec 1 x = 5")
    assert "expected a field rule" in item.message


def test_spec_header_is_the_single_language_version():
    assert Catalog.from_string('spec 1 x = one of "a" resource r { name = "{x}" }')
    assert [d.code for d in diagnostics('spec 2 x = one of "a" resource r { name = "{x}" }')] == [
        "unsupported_spec"
    ]
    assert [d.code for d in diagnostics("spec one")] == ["syntax_error"]


def test_string_escapes_keep_regex_backslashes():
    assert unescape(r"\d+") == r"\d+"
    assert unescape(r"a\"b") == 'a"b'
    assert unescape(r"it\'s") == "it's"
    assert unescape(r"C:\\x") == r"C:\x"
    assert unescape("trailing\\") == "trailing\\"
    catalog = Catalog.from_string(
        r"""spec 1
        digits = text matching "\d+" examples "42"
        quoted = text matching "[a-z\"]+" examples "say\"hi"
        single = text matching '[a-z\']+' examples "it's"
        resource r { name = "{digits}.{quoted}.{single}" }
        """
    )
    assert catalog.parse("42.say\"hi.it's").fields["digits"] == "42"
    assert catalog.definition.fields["digits"].pattern == r"\d+"


def test_tokens_track_lines_through_comments_and_crlf():
    tokens = tokenize('spec 1 // header\r\n// whole line\r\nx = one of "a"\r\n')
    assert [token.value for token in tokens] == ["spec", 1, "x", "=", "one", "of", "a", None]
    assert [(token.line, token.column) for token in tokens[:3]] == [(1, 1), (1, 6), (3, 1)]
    assert tokens[-1].kind == "eof" and tokens[-1].line == 4
    assert Catalog.from_string('spec 1\r\nx = one of "a"\r\nresource r { name = "{x}" } // end')


def test_resource_entries_in_any_order_and_integers_may_be_negative():
    catalog = Catalog.from_string(
        """spec 1
        resource r {
            meta { kind = "file" tags = [] }
            location = "/{job}/{name}"
            reader = readers[ext]
            name = "{job}.{ext}"
        }
        readers { abc = "alembic" }
        job = text matching "[a-z]+" examples "job"
        ext = one of "abc"
        """
    )
    spec = catalog.definition.resources["r"]
    assert spec.template == "{job}.{ext}" and spec.location == "/{job}/{name}"
    assert spec.reader_field == "ext" and spec.metadata == {"kind": "file", "tags": ()}
    assert [d.code for d in diagnostics('spec 1 r { name = "{x}" } x = integer minimum -1')] == [
        "syntax_error"
    ]
    assert [
        d.code for d in diagnostics('spec 1 resource r { name = "{x}" } x = integer minimum -1')
    ] == ["invalid_integer"]


R = 'x = one of "a" resource r { name = "{x}" }'


@pytest.mark.parametrize(
    "source,code",
    [
        ('spec 1 resource = one of "a" resource r { name = "{resource}" }', "reserved_field"),
        ('spec 1 meta = one of "a" resource r { name = "{meta}" }', "reserved_field"),
        ('spec 1 normalize { slashes = "back" } ' + R, "invalid_normalize"),
        ('spec 1 normalize { case = "upper" } ' + R, "invalid_normalize"),
        ('spec 1 normalize { drive = "upper" drive = "lower" } ' + R, "duplicate_definition"),
        ('spec 1 readers { abc = "" } ' + R, "empty_handler"),
        (
            'spec 1 resource r { name = "{x}" meta { k = 1 k = 2 } } x = one of "a"',
            "duplicate_definition",
        ),
        (
            'spec 1 resource r { location = "/{x}" reader = readers[x] } x = one of "a" '
            'readers { a = "h" }',
            "invalid_reader",
        ),
    ],
)
def test_declaration_rules(source, code):
    assert [item.code for item in diagnostics(source)] == [code]


def test_keywords_in_other_positions_are_ordinary_identifiers():
    catalog = Catalog.from_string(
        """spec 1
        text = one of "a"
        input = one of "b"
        location = text matching "[c]" examples "c"
        resource r { name = "{text}_{input}_{location}" }
        """
    )
    assert catalog.parse("a_b_c").fields == {"text": "a", "input": "b", "location": "c"}
