"""Guard the editable test contract against silent omissions and typing mistakes."""

import csv

import case_data
import pytest


@pytest.fixture
def table(tmp_path, monkeypatch):
    with (case_data.CASE_DIRECTORY / "assets.csv").open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames
        rows = list(reader)
    (tmp_path / "examples").mkdir()
    (tmp_path / "examples" / "assets.names").touch()
    monkeypatch.setattr(case_data, "ROOT", tmp_path)
    return tmp_path / "assets.csv", headers, rows


def write_table(path, headers, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def test_csv_preserves_types_absence_and_visible_whitespace(table):
    path, headers, rows = table
    write_table(path, headers, rows)
    cases = {case.id: case for case in case_data.load_cases(path)}
    assert cases["assets/donut_alembic"].fields["version"] == 4
    assert type(cases["assets/donut_alembic"].fields["version"]) is int
    assert "lod" not in cases["assets/unknown_lod"].fields
    assert cases["assets/trailing_newline"].input.endswith("\n")


@pytest.mark.parametrize(
    "column,value,message",
    [
        ("valid", "yes", "true/false"),
        ("field.version:int", "four", "invalid literal"),
        ("diagnostics", "invalid_field:version", "valid rows need no diagnostics"),
        ("source", "filename", "source must be"),
    ],
)
def test_bad_expectations_fail_with_row_location(table, column, value, message):
    path, headers, rows = table
    rows[0][column] = value
    write_table(path, headers, rows)
    with pytest.raises(ValueError, match=message) as exc:
        case_data.load_cases(path)
    assert "assets.csv:2 (donut_alembic)" in str(exc.value)


def test_duplicate_ids_are_not_silently_overwritten(table):
    path, headers, rows = table
    rows.append(rows[0])
    write_table(path, headers, rows)
    with pytest.raises(ValueError, match="unique"):
        case_data.load_cases(path)


def test_typo_in_column_does_not_skip_expectations(table):
    path, headers, rows = table
    headers.append("filed.asset_name")
    write_table(path, headers, rows)
    with pytest.raises(ValueError, match="metadata column"):
        case_data.load_cases(path)


def test_missing_cell_is_not_treated_as_absent_metadata(table):
    path, headers, _ = table
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerow(["incomplete", "Donut_high_v004.abc"])
    with pytest.raises(ValueError, match="wrong number of cells"):
        case_data.load_cases(path)


def test_tables_can_share_a_schema_and_assert_ambiguity(table):
    path, headers, rows = table
    path = path.with_name("another_table.csv")
    headers += ["schema", "matches"]
    rows = [dict(rows[0], schema="assets", matches="asset_model;another_resource")]
    write_table(path, headers, rows)
    case = case_data.load_cases(path)[0]
    assert case.schema.name == "assets.names"
    assert case.matches == ("asset_model", "another_resource")


@pytest.mark.parametrize(
    "column,value,message",
    [
        ("schema", "../assets", "simple name"),
        ("schema", "absent_schema", "missing matching schema"),
        ("matches", "another_resource", "including resource"),
        ("matches", "asset_model;asset_model", "unique resource"),
    ],
)
def test_bad_schema_or_match_expectations_fail(table, column, value, message):
    path, headers, rows = table
    headers.append(column)
    rows[0][column] = value
    write_table(path, headers, rows)
    with pytest.raises(ValueError, match=message):
        case_data.load_cases(path)
