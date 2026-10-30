"""Cross-feature invariants supplement the independently authored convention tables."""

from hypothesis import given, settings
from hypothesis import strategies as st

from namespec import Catalog, NameSpecError

LETTERS = st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=20)
CATALOG = Catalog.from_string(
    """spec 1
roots { win = "c:/jobs" }
normalize { drive = "upper" slashes = "forward" }
asset = text matching "[a-z]+"
tag = text matching "[a-z]+"
artist = text matching "[a-z]+"
version = integer minimum -10000 maximum 10000 padded to 4 digits
Asset = "{asset}[_{tag}_{artist}]"
resource model { name = "{Asset}_v{version}.abc" location = "{root}/{name}" }
""",
    strict=True,
)


@given(LETTERS, st.integers(-10000, 10000), st.one_of(st.none(), st.tuples(LETTERS, LETTERS)))
def test_names_locations_and_optional_composites_roundtrip(asset, version, optional):
    values = {"asset": asset, "version": version}
    if optional is not None:
        values.update(tag=optional[0], artist=optional[1])
    name = CATALOG.format("model", values)
    parsed = CATALOG.parse(name, "model")
    for field, value in values.items():
        assert parsed.fields[field] == value
    assert parsed.name == name
    path = parsed.locate(root="win")
    assert CATALOG.parse(path, "model", source="location").fields == {
        "root": "C:/jobs",
        **parsed.fields,
    }
    changed = parsed.replace(version=-version)
    assert changed.fields["version"] == -version
    assert parsed.fields["version"] == version


@given(st.text(max_size=100))
def test_normalization_is_idempotent_and_preserves_offsets(text):
    normalized = CATALOG.normalize(text)
    assert CATALOG.normalize(normalized) == normalized
    assert len(normalized) == len(text)


@given(st.text(max_size=80))
@settings(max_examples=150)
def test_invalid_names_produce_diagnostics_instead_of_implementation_exceptions(text):
    result = CATALOG.validate(text, "model", source="name")
    if result.valid:
        assert CATALOG.parse(text, "model", source="name").name == text
    else:
        assert result.diagnostics
        try:
            CATALOG.parse(text, "model", source="name")
        except NameSpecError as exc:
            assert exc.diagnostics == list(result.diagnostics)
        else:
            raise AssertionError("parse accepted a failed validation")


@given(st.integers(min_value=1, max_value=4), st.booleans())
def test_optional_sample_groups_never_generate_partial_values(size, composite):
    declarations = " ".join(f'p{i} = one of "a", "b"' for i in range(size))
    slots = "_".join(f"{{p{i}}}" for i in range(size))
    group = f"[{'_' + slots}]"
    if composite:
        declarations += f' C = "{slots}"'
        group = "[_{C}]"
    catalog = Catalog.from_string(
        f'spec 1 x = one of "x" {declarations} resource r {{ name = "{{x}}{group}" }}',
        strict=True,
    )
    samples = list(catalog.samples("r", limit=32))
    assert len(samples) == 1 + 2**size
    for name in samples:
        assert catalog.validate(name, "r").valid


@given(LETTERS, LETTERS)
def test_isolated_regex_anchors_do_not_bind_to_the_surrounding_template(left, right):
    catalog = Catalog.from_string(
        """spec 1
    x = text matching "^[a-z]+_[a-z]+$"
    resource r { name = "prefix_{x}.abc" }
    """,
        strict=True,
    )
    value = f"{left}_{right}"
    text = catalog.format("r", x=value)
    assert catalog.parse(text, "r").fields == {"x": value}
