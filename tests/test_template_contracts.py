"""Contracts shared by field validation, parsing, generation and composite expansion."""

from __future__ import annotations

import subprocess
import sys

import pytest

from namespec import Catalog, NameSpecError
from namespec.template import Template


@pytest.mark.parametrize(
    "rule,separator",
    [(r'text matching "[^.]+"', item) for item in ("/", "\\", "\n", "\r")]
    + [('one of "VALUE"', item) for item in ("/", "\\", "\r")],
)
def test_path_separators_are_rejected_by_every_field_operation(rule, separator):
    value = f"a{separator}b"
    source = 'spec 1 x = RULE resource r { name = "{x}.txt" }'
    source = source.replace("RULE", rule.replace("VALUE", value.replace("\\", "\\\\")))
    catalog = Catalog.from_string(source)
    for result in (
        catalog.validate(value + ".txt", "r", source="name"),
        catalog.validate_field("x", value),
    ):
        assert not result.valid
        assert result.diagnostics[0].code == "reserved_separator"
        assert "x" not in result.fields
    for operation in (
        lambda: catalog.format("r", x=value),
        lambda: catalog.format_field("x", value),
        lambda: catalog.parse(value + ".txt", "r", source="name"),
    ):
        with pytest.raises(NameSpecError) as exc:
            operation()
        assert exc.value.diagnostics[0].code == "reserved_separator"


@pytest.mark.parametrize(
    "pattern,value",
    [
        ("(?i)[a-z]+", "AbC"),
        ("(?u)[a-z]+", "abc"),
        ("(?P<f0>[a-z]+)", "abc"),
        (r"([a-z])\1", "aa"),
        (r"(?P<word>[a-z]+)_(?P=word)", "abc_abc"),
        ("^[a-z]+_[a-z]+$", "foo_bar"),
        (r"\bfoo_bar\b", "foo_bar"),
        ("(?<!_)foo_bar", "foo_bar"),
        ("(?=foo_bar$)[a-z_]+", "foo_bar"),
    ],
)
def test_standalone_regex_semantics_survive_prefixes_and_repeated_slots(pattern, value):
    catalog = Catalog.from_string(
        f'spec 1 x = text matching "{pattern}" '
        'resource r { name = "prefix_{x}_{x}.txt" location = "/{x}/{name}" }'
    )
    name = catalog.format("r", x=value)
    assert catalog.parse(name, "r").fields == {"x": value}
    path = catalog.locate("r", x=value)
    assert catalog.parse(path, "r", source="location").fields == {"x": value}
    assert catalog.validate_field("x", value).valid


def test_isolated_rules_preserve_diagnostics_spans_and_optional_groups():
    catalog = Catalog.from_string(
        'spec 1 x = text matching "^[a-z]+_[a-z]+$" '
        'tag = one of "tag" ext = one of "txt" '
        'resource r { name = "{x}[_{tag}].{ext}" location = "/{x}/{name}" }'
    )
    assert catalog.parse("foo_bar.txt", "r").fields == {"x": "foo_bar", "ext": "txt"}
    assert catalog.parse("foo_bar_tag.txt", "r").fields["tag"] == "tag"
    text = "/foo_bar/foo_baz_wrong.txt"
    result = catalog.validate(text, "r", source="location")
    assert {(item.code, item.field) for item in result.diagnostics} == {
        ("conflicting_field", "x"),
        ("invalid_field", "tag"),
    }
    assert {text[slice(*item.span)] for item in result.diagnostics} == {"foo_baz", "wrong"}


def test_field_lookarounds_do_not_read_neighboring_literals():
    catalog = Catalog.from_string(
        'spec 1 x = text matching "(?!v[0-9]+$)[a-z][A-Za-z0-9]*" resource r { name = "{x}_tail" }'
    )
    result = catalog.validate("v012_tail", "r")
    assert not result.valid
    assert [(item.code, item.field) for item in result.diagnostics] == [("invalid_field", "x")]


@pytest.mark.parametrize(
    "rule,text,expected",
    [
        ('text matching "[a-z_]+?"', "aa_bb_cc.nk", {"a": "aa", "b": "bb_cc", "ext": "nk"}),
        ('one of "a", "a_b"', "a_b_c.nk", {"a": "a", "b": "b_c", "ext": "nk"}),
        (
            'text matching "(?:a|a_b)"',
            "a_b_c.nk",
            {"a": "a", "b": "b_c", "ext": "nk"},
        ),
    ],
)
def test_other_fields_keep_their_regex_preference_when_one_rule_needs_isolation(
    rule, text, expected
):
    source = (
        f'spec 1 a = {rule} b = text matching "[a-z_]+" '
        'ext = EXT resource r { name = "{a}_{b}.{ext}" }'
    )
    for extension in ('one of "nk"', 'text matching "^nk$"'):
        catalog = Catalog.from_string(source.replace("EXT", extension))
        assert catalog.parse(text, "r").fields == expected


@pytest.mark.parametrize("pattern", ["[a-z/]+", "(?i)[a-z/]+"])
def test_permissive_fields_do_not_consume_an_optional_path_separator(pattern):
    catalog = Catalog.from_string(
        f'spec 1 a = text matching "{pattern}" b = one of "y" '
        'resource r { location = "{a}[/{b}]" }',
        strict=True,
    )
    text = catalog.locate("r", a="x", b="y")
    assert text.as_posix() == "x/y"
    assert catalog.parse(text, "r", source="location").fields == {"a": "x", "b": "y"}
    assert catalog.parse("x", "r", source="location").fields == {"a": "x"}


def test_explicitly_removed_composites_conflict_with_supplied_descendants():
    catalog = Catalog.from_string(
        'spec 1 task = one of "base" x = one of "a" y = one of "b" '
        'C = "{x}_{y}" Outer = "{C}" resource r { name = "{task}[_{Outer}].txt" }'
    )
    resource = catalog.parse("base_a_b.txt", "r")
    for changes in ({"C": None, "x": "a", "y": "b"}, {"Outer": "a_b", "C": None}):
        for operation in (
            lambda changes=changes: resource.replace(**changes),
            lambda changes=changes: list(catalog.samples("r", **changes)),
            lambda changes=changes: catalog.format("r", task="base", **changes),
        ):
            with pytest.raises(NameSpecError) as exc:
                operation()
            assert "conflicting_field" in {item.code for item in exc.value.diagnostics}
    assert resource.replace(Outer=None).name == "base.txt"
    assert list(catalog.samples("r", Outer=None)) == ["base.txt"]


@pytest.mark.parametrize("name,code", [("a_B.txt", "invalid_field"), ("a_.txt", "missing_field")])
def test_invalid_optional_parts_omit_every_owning_composite(name, code):
    catalog = Catalog.from_string(
        'spec 1 x = text matching "[a-z]+" tag = text matching "[a-z]+" '
        'Inner = "{x}[_{tag}]" Outer = "{Inner}" resource r { name = "{Outer}.txt" }'
    )
    result = catalog.validate(name, "r")
    assert result.fields == {"x": "a"}
    assert [(item.code, item.field) for item in result.diagnostics] == [(code, "tag")]
    assert catalog.parse("a.txt", "r").fields == {"x": "a", "Inner": "a", "Outer": "a"}


def test_composite_compilation_is_shared_across_a_deep_chain(monkeypatch):
    count = 0
    original = Template.__init__

    def counted(self, *args, **kwargs):
        nonlocal count
        count += 1
        original(self, *args, **kwargs)

    monkeypatch.setattr(Template, "__init__", counted)
    depth = 30
    fields = ['x = one of "a"']
    for index in range(depth):
        parent = "x" if index == 0 else f"c{index - 1}"
        fields.append(f'c{index} = "{{{parent}}}"')
    source = "spec 1 " + " ".join(fields) + f' resource r {{ name = "{{c{depth - 1}}}" }}'
    Catalog.from_string(source)
    assert count <= depth + 1
    # Bound the validation check too: recursively rebuilding already-decoded composites
    # used to take exponential time independently of compilation.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from namespec import Catalog; "
            f"print(Catalog.from_string(sys.argv[1]).parse('a', 'r').fields['c{depth - 1}'])",
            source,
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert result.stdout.strip() == "a"


def test_literal_brackets_and_optional_brackets_coexist():
    catalog = Catalog.from_string(
        'spec 1 x = one of "a" tag = one of "b" '
        'resource r { name = "[[{x}]][_{tag}].txt" location = "/[[folder]]/{name}" }'
    )
    assert catalog.format("r", x="a") == "[a].txt"
    assert catalog.format("r", x="a", tag="b") == "[a]_b.txt"
    assert catalog.parse("[a].txt", "r").fields == {"x": "a"}
    assert catalog.parse("/[folder]/[a]_b.txt", "r", source="location").fields == {
        "x": "a",
        "tag": "b",
    }


def test_strict_format_detects_metadata_changed_by_greedy_field_boundaries():
    catalog = Catalog.from_string(
        'spec 1 x = text matching "[a-z_]+" y = text matching "[a-z_]+" '
        'resource r { name = "{x}_{y}" }'
    )
    template = catalog._names["r"]
    assert template.format({"x": "a", "y": "b_c"}) == "a_b_c"
    with pytest.raises(NameSpecError) as exc:
        template.format({"x": "a", "y": "b_c"}, strict=True)
    assert {item.code for item in exc.value.diagnostics} == {"non_roundtripping_value"}
    assert template.format({"x": "a_b", "y": "c"}, strict=True) == "a_b_c"


def test_signed_integer_padding_counts_digits_and_respects_maximum():
    catalog = Catalog.from_string(
        "spec 1 frame = integer minimum -100 maximum 100 padded to 3 digits "
        'resource r { name = "frame-{frame}.exr" }'
    )
    assert catalog.format("r", frame=-7) == "frame--007.exr"
    assert catalog.parse("frame--007.exr", "r").fields == {"frame": -7}
    assert catalog.validate_field("frame", "007").fields == {"frame": 7}
    for text, code in (
        ("-7", "noncanonical_field"),
        ("-000", "noncanonical_field"),
        ("+007", "invalid_field"),
        ("101", "invalid_field"),
    ):
        assert catalog.validate_field("frame", text).diagnostics[0].code == code


def test_oversized_integer_inputs_report_diagnostics():
    catalog = Catalog.from_string('spec 1 n = integer minimum 0 resource r { name = "{n}" }')
    limit = getattr(sys, "get_int_max_str_digits", lambda: 0)()
    if not limit:
        pytest.skip("this interpreter does not impose an integer digit limit")
    result = catalog.validate("1" * (limit + 1), "r")
    assert not result.valid
    assert result.diagnostics[0].code == "invalid_integer"
    for operation in (
        lambda: catalog.format("r", n=10 ** (limit + 1)),
        lambda: catalog.format_field("n", 10 ** (limit + 1)),
    ):
        with pytest.raises(NameSpecError) as exc:
            operation()
        assert exc.value.diagnostics[0].code == "invalid_integer"
        assert exc.value.diagnostics[0].actual is None
