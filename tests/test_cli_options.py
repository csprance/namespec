import json

import pytest

from namespec.cli import main


def test_cli_strict_roundtrip_option(tmp_path, capsys):
    rules = tmp_path / "rules.names"
    rules.write_text(
        """spec 1
    x = text matching "[a-z_]+"
    y = text matching "[a-z_]+"
    resource r { name = "{x}_{y}" }
    """,
        encoding="utf-8",
    )
    args = [str(rules), "--strict", "format", "r", '{"x":"a","y":"b_c"}']
    assert main(args) == 2
    assert (
        json.loads(capsys.readouterr().out)["diagnostics"][0]["code"] == "non_roundtripping_value"
    )


def test_cli_filesystem_option(tmp_path, capsys):
    pytest.importorskip("pathvalidate")
    rules = tmp_path / "rules.names"
    rules.write_text('spec 1 x = text matching ".+" resource r { name = "{x}" }', encoding="utf-8")
    assert main([str(rules), "--filesystem", "portable", "inspect", "CON.txt"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "invalid"


def test_cli_bad_file_encoding_is_reported_without_traceback(tmp_path, capsys):
    rules = tmp_path / "bad.names"
    rules.write_bytes(b"\xff")
    assert main([str(rules), "test", "--json"]) == 2
    assert "error" in json.loads(capsys.readouterr().out)


@pytest.fixture
def location_rules(tmp_path):
    rules = tmp_path / "locations.names"
    rules.write_text(
        """spec 1
        x = one of "item"
        normalize { slashes = "forward" drive = "upper" }
        resource r { name = "{x}.txt" location = "J:/jobs/{name}" }
        """,
        encoding="utf-8",
    )
    return rules


@pytest.mark.parametrize("resource_args", [[], ["--resource", "r"]])
@pytest.mark.parametrize("source_args", [[], ["--source", "auto"]])
def test_cli_inspect_detects_location_without_a_source_override(
    location_rules, capsys, resource_args, source_args
):
    assert (
        main([str(location_rules), "inspect", r"j:\jobs\item.txt", *resource_args, *source_args])
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    result = report if resource_args else report["matches"][0]
    assert result["valid"]
    assert result["source"] == "location"
    assert result["resource"] == "r"
    assert result["input"] == "J:/jobs/item.txt"
    assert result["fields"] == {"x": "item"}


def test_cli_inspect_still_accepts_names_and_explicit_source_selection(location_rules, capsys):
    assert main([str(location_rules), "inspect", "item.txt"]) == 0
    [result] = json.loads(capsys.readouterr().out)["matches"]
    assert result["source"] == "name" and result["fields"] == {"x": "item"}
    assert (
        main(
            [
                str(location_rules),
                "inspect",
                "J:/jobs/item.txt",
                "--resource",
                "r",
                "--source",
                "name",
            ]
        )
        == 1
    )
    report = json.loads(capsys.readouterr().out)
    assert not report["valid"] and report["source"] == "name"
    assert report["diagnostics"][0]["code"] == "pattern_mismatch"


def test_cli_locate_serializes_path_as_canonical_json_text(location_rules, capsys):
    assert main([str(location_rules), "locate", "r", '{"x":"item"}']) == 0
    assert json.loads(capsys.readouterr().out) == {"locate": "J:/jobs/item.txt"}
    assert main([str(location_rules), "format", "r", '{"x":"item"}']) == 0
    assert json.loads(capsys.readouterr().out) == {"format": "item.txt"}
