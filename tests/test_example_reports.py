"""Failing examples and broken rules say what is wrong and point at the text to fix."""

from __future__ import annotations

import io
import json
import sys

import pytest

from namespec import Catalog, NameSpecError
from namespec.cli import main

RULES = """spec 1
asset = text matching "[A-Z][a-z]+" examples "Donut"
lod = one of "low", "high"
version = integer minimum 1 padded to 3 digits
tag = text matching "[a-z]+"
resource model { name = "{asset}_{lod}_v{version}[_{tag}].abc" }
example model {
    input = "Donut_high_v004.abc"
    expect { asset = "Donut" lod = "high" version = 4 }
}
"""
GOOD = 'expect { asset = "Donut" lod = "high" version = 4 }'


def failures(source):
    """Each failure's message with the rule text its span covers."""
    return [
        (item.message, source[slice(*item.span)])
        for item in Catalog.from_string(source).check_examples()
    ]


def rejected(source):
    with pytest.raises(NameSpecError) as exc:
        Catalog.from_string(source)
    [item] = exc.value.diagnostics
    return item.code, source[slice(*item.span)], str(exc.value)


def test_passing_examples_report_the_block_they_came_from():
    source = RULES + 'reject model { input = "Donut_mid_v004.abc" expect = "invalid_field" }\n'
    results = Catalog.from_string(source).run_examples()
    assert [result.passed for result in results] == [True, True]
    blocks = [source[slice(*result.span)] for result in results]
    assert blocks[0].startswith("example model {") and blocks[0].endswith("}")
    assert blocks[1] == source.splitlines()[-1]


def test_a_wrong_expected_value_points_at_that_field():
    source = RULES.replace('lod = "high" version', 'lod = "low" version')
    assert failures(source) == [('Expected lod = "low", got "high".', 'lod = "low"')]


def test_a_quoted_number_or_bare_text_says_how_to_write_it():
    source = RULES.replace("version = 4", 'version = "4"')
    assert failures(source) == [
        (
            'Expected version = "4", got 4. version is a number, so write it without quotes.',
            'version = "4"',
        )
    ]
    digits = (
        'spec 1\ncode = text matching "[0-9]+"\nresource r { name = "{code}" }\n'
        'example r { input = "7" expect { code = 7 } }\n'
    )
    assert failures(digits) == [
        ('Expected code = 7, got "7". code is text, so quote it.', "code = 7")
    ]


def test_fields_the_name_lacks_or_the_example_left_out():
    source = RULES.replace("version = 4 }", 'version = 4 tag = "wip" }')
    assert failures(source) == [('Expected tag = "wip", but this model has no tag.', 'tag = "wip"')]
    source = RULES.replace("v004.abc", "v004_wip.abc")
    assert failures(source) == [('Missing from expect: tag = "wip"', GOOD.removeprefix("expect "))]


def test_a_name_that_does_not_parse_points_at_the_input():
    source = RULES.replace("Donut_high_v004", "Donut_mid_v004")
    [(message, text)] = failures(source)
    assert message == "Not a valid model: Invalid 'lod'; expected one of ('low', 'high')."
    assert text == '"Donut_mid_v004.abc"'


def test_rejections_say_what_happened_instead():
    valid = RULES + 'reject model { input = "Donut_high_v004.abc" expect = "invalid_field" }\n'
    assert failures(valid) == [
        ("Expected invalid_field, but this is a valid model.", '"Donut_high_v004.abc"')
    ]
    other = RULES + 'reject model { input = "Donut_high_v4.abc" expect = "invalid_field" }\n'
    assert failures(other) == [
        (
            "Expected invalid_field, got noncanonical_field: "
            "'version' must use canonical numeric padding.",
            '"Donut_high_v4.abc"',
        )
    ]


def test_broken_rules_point_at_the_declaration():
    code, text, message = rejected(RULES.replace('examples "Donut"', 'examples "Donut", "pie"'))
    assert (code, text) == ("invalid_sample", '"pie"')
    assert message == "line 2, column 55: Sample 'pie' for 'asset' does not match '[A-Z][a-z]+'."
    code, text, _ = rejected(RULES.replace("{lod}", "{lodd}"))
    assert code == "unknown_field"
    assert text == 'name = "{asset}_{lodd}_v{version}[_{tag}].abc"'
    code, text, _ = rejected(RULES.replace('"[a-z]+"', '"[a-z"'))
    assert code == "invalid_pattern" and text == 'tag = text matching "[a-z"'
    code, text, _ = rejected(RULES.replace("example model", "example modle"))
    assert (code, text) == ("unknown_resource", "modle")
    code, text, _ = rejected(RULES.replace("    input =", "    location ="))
    assert (code, text) == ("missing_location", '"Donut_high_v004.abc"')
    code, text, _ = rejected(RULES.replace("version = 4", "version = 4 lod = 'x'"))
    assert (code, text) == ("duplicate_definition", "lod = 'x'")


def test_cli_reads_unsaved_rules_from_stdin_with_exact_offsets(monkeypatch, capsys):
    # A CRLF buffer with a character outside ASCII before the failure keeps its offsets.
    source = "// café\n" + RULES.replace('lod = "high" version', 'lod = "low" version')
    source = source.replace("\n", "\r\n")
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(source.encode("utf-8"))))
    assert main(["-", "test", "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    [example] = report["examples"]
    assert (example["kind"], example["passed"], example["line"]) == ("example", False, 8)
    [failure] = example["failures"]
    assert source[slice(*failure["span"])] == 'lod = "low"'
    assert (failure["field"], failure["line"], failure["column"]) == ("lod", 10, 30)


def test_cli_reports_broken_rules_by_line(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "rules.names").write_text(RULES.replace("{lod}", "{lodd}"), encoding="utf-8")
    assert main(["rules.names", "test"]) == 2
    assert capsys.readouterr().out == (
        "rules.names:6:18: Unknown field 'lodd' in '{asset}_{lodd}_v{version}[_{tag}].abc'.\n"
    )
    assert main(["rules.names", "test", "--json"]) == 2
    [item] = json.loads(capsys.readouterr().out)["diagnostics"]
    assert (item["code"], item["line"], item["column"]) == ("unknown_field", 6, 18)
    assert main(["missing.names", "test"]) == 2
    assert capsys.readouterr().out.startswith("missing.names: ")


def test_cli_with_nothing_to_run(tmp_path, capsys):
    rules = tmp_path / "rules.names"
    rules.write_text(RULES.split("example model")[0], encoding="utf-8")
    assert main([str(rules), "test"]) == 0
    assert capsys.readouterr().out == "No examples to run.\n"


def test_positions_stay_out_of_the_export():
    model = Catalog.from_string(RULES).definition.to_dict()
    assert "spans" not in model
    json.dumps(model)
