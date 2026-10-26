"""Bidirectional templates with deterministic token boundaries and field diagnostics."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from string import Formatter
from typing import Any

from .models import Diagnostic, FieldSpec, NameSpecError, Validation, fail

try:  # Python 3.11+
    from re import _parser as _sre  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - Python 3.10
    import sre_parse as _sre  # type: ignore[no-redef]

ROOT = "root"


def field_value(spec: FieldSpec, value: Any, *, parsing: bool) -> str | int:
    """Validate a logical value or decode one field's spelling in a name."""
    details = {"field": spec.name, "actual": value}
    if value is None or value == "":
        fail("missing_field", f"Missing {spec.name!r}.", **details)
    if spec.kind == "integer":
        if parsing:
            if not re.fullmatch(r"[0-9]+", value):
                fail("invalid_field", f"{spec.name!r} must contain ASCII digits.", **details)
            number = int(value)
        elif type(value) is int:
            number = value
        else:
            fail("invalid_type", f"{spec.name!r} requires an integer.", **details)
        if number < spec.minimum:
            fail(
                "invalid_field",
                f"{spec.name!r} must be at least {spec.minimum}.",
                expected=spec.minimum,
                **details,
            )
        if parsing and value != str(number).zfill(spec.width):
            fail(
                "noncanonical_field",
                f"{spec.name!r} must use canonical numeric padding.",
                expected=str(number).zfill(spec.width),
                **details,
            )
        return number
    if not isinstance(value, str):
        fail("invalid_type", f"{spec.name!r} requires text.", **details)
    if spec.kind == "enum" and value not in spec.choices:
        fail(
            "invalid_field",
            f"Invalid {spec.name!r}; expected one of {spec.choices}.",
            expected=list(spec.choices),
            **details,
        )
    if spec.kind == "text" and not re.fullmatch(spec.pattern, value):
        fail(
            "invalid_field",
            f"{spec.name!r} does not match {spec.pattern!r}.",
            expected=spec.pattern,
            **details,
        )
    return value


def spelling(spec: FieldSpec, value: str | int) -> str:
    """The canonical text of a logical value inside a name."""
    return str(value).zfill(spec.width) if spec.kind == "integer" else value


def parse_parts(text: str) -> list[tuple[str, str | None, str | None, str | None]]:
    try:
        return list(Formatter().parse(text))
    except ValueError as exc:
        fail("invalid_template", str(exc))


def split_groups(text: str) -> list[tuple[str, bool]]:
    """Split a template into plain and optional ``[...]`` segments. Groups do not nest."""
    segments: list[tuple[str, bool]] = []
    current: list[str] = []
    inside = False
    for character in text:
        if character == "[":
            if inside:
                fail("invalid_template", f"Optional groups cannot nest in {text!r}.")
            segments.append(("".join(current), False))
            current, inside = [], True
        elif character == "]":
            if not inside:
                fail("invalid_template", f"Unmatched ']' in {text!r}.")
            segments.append(("".join(current), True))
            current, inside = [], False
        else:
            current.append(character)
    if inside:
        fail("invalid_template", f"Unmatched '[' in {text!r}.")
    segments.append(("".join(current), False))
    return [(segment, optional) for segment, optional in segments if segment or optional]


def has_punctuation(literal: str) -> bool:
    return any(not character.isalnum() for character in literal)


def slot_pattern(spec: FieldSpec) -> str:
    """The regex a field's own rule implies, for the precise template pattern."""
    if spec.kind == "integer":
        return "[0-9]+"
    if spec.kind == "enum":
        return "|".join(map(re.escape, spec.choices))
    return spec.pattern or ""


def may_contain(spec: FieldSpec, characters: frozenset[str]) -> bool:
    """Can a value of this field include any of these characters?

    Decided once per template from the rule itself, so the fallback matcher only pays for
    backtracking on the few fields whose rule crosses the template's punctuation.
    """
    if spec.kind == "integer":
        return False
    if spec.kind == "enum":
        return any(character in choice for choice in spec.choices for character in characters)
    return pattern_may_match(spec.pattern or "", characters)


def pattern_may_match(pattern: str, characters: frozenset[str]) -> bool:
    """Whether any atom of a regex could consume one of the given characters.

    Walks the parse tree the ``re`` module builds. Anything it does not understand counts as
    able to match, which only costs a slower fallback for that one field.
    """
    try:
        tree = _sre.parse(pattern)
    except Exception:  # noqa: BLE001 - re.error and friends; the rule was compiled already
        return True
    return _walk(tree, characters)


def _walk(items: Any, characters: frozenset[str]) -> bool:
    for op, av in items:
        if op is _sre.LITERAL:
            if chr(av) in characters:
                return True
        elif op is _sre.NOT_LITERAL:
            if any(chr(av) != character for character in characters):
                return True
        elif op is _sre.ANY:
            return True
        elif op is _sre.IN:
            if _set_may_match(av, characters):
                return True
        elif op in (_sre.MAX_REPEAT, _sre.MIN_REPEAT) or op is getattr(
            _sre, "POSSESSIVE_REPEAT", None
        ):
            if _walk(av[2], characters):
                return True
        elif op is _sre.SUBPATTERN:
            if _walk(av[3], characters):
                return True
        elif op is getattr(_sre, "ATOMIC_GROUP", None):
            if _walk(av, characters):
                return True
        elif op is _sre.BRANCH:
            if any(_walk(branch, characters) for branch in av[1]):
                return True
        elif op is _sre.GROUPREF_EXISTS:
            if _walk(av[1], characters) or (av[2] and _walk(av[2], characters)):
                return True
        elif op in (_sre.AT, _sre.ASSERT, _sre.ASSERT_NOT):
            continue  # zero width
        else:
            return True  # back-references and anything newer: assume it can
    return False


def _set_may_match(items: Any, characters: frozenset[str]) -> bool:
    negate = False
    matched: set[str] = set()
    for op, av in items:
        if op is _sre.NEGATE:
            negate = True
        elif op is _sre.LITERAL:
            matched.add(chr(av))
        elif op is _sre.RANGE:
            matched.update(c for c in characters if av[0] <= ord(c) <= av[1])
        elif op is _sre.CATEGORY:
            matched.update(c for c in characters if _category(av, c))
        else:
            return True
    return any((character in matched) != negate for character in characters)


def _category(category: Any, character: str) -> bool:
    name = str(category).rsplit(".", 1)[-1].replace("CATEGORY_", "")
    negated = name.startswith("NOT_")
    name = name.removeprefix("NOT_")
    if name.endswith("DIGIT"):
        hit = character.isdigit()
    elif name.endswith("SPACE"):
        hit = character.isspace()
    elif name.endswith("WORD"):
        hit = character.isalnum() or character == "_"
    else:
        hit = True
    return hit != negated


PATH_SEPARATORS = frozenset({"/", "\\", "\n", "\r"})


@dataclass(frozen=True)
class Slot:
    """One captured leaf field, the composite it was expanded from, and its optional group."""

    name: str
    composite: str | None = None
    group: int | None = None


@dataclass(frozen=True)
class GroupStart:
    index: int


@dataclass(frozen=True)
class GroupEnd:
    index: int


@dataclass
class Group:
    index: int
    names: tuple[str, ...] = ()


class Template:
    """Literal text, {field} slots and optional [..] groups. Delimiters are reserved in values.

    Reserving delimiters keeps structural extraction independent of field validation:
    a misspelled enum can still be attached to the correct field, without guessing.
    Composite fields expand to their parts before the pattern is built, so a `{Shot}` slot
    captures `Episode`, `seqnum` and `shotnum` separately and repeats are checked per part.
    `{root}` is a location-only prefix matched against the declared roots as literals.
    An optional group matches as a whole or not at all; its fields are then absent.
    """

    def __init__(
        self, text: str, fields: dict[str, FieldSpec], *, roots: Mapping[str, str] | None = None
    ):
        self.text = text
        self.fields = fields
        self.roots = dict(roots) if roots is not None else None
        self.has_root = False
        self.slots: list[Slot] = []
        self.groups: list[Group] = []
        self.composites: list[str] = []
        self._pieces: list[str | Slot | GroupStart | GroupEnd] = []
        self._leaves_of: dict[str, set[str]] = {}
        self._separated = True
        self._group: int | None = None
        self._expand(text, None, ())
        self.names: list[str] = [slot.name for slot in self.slots]
        if not self.names:
            fail("invalid_template", "A template must contain at least one field.")
        self.required = frozenset(slot.name for slot in self.slots if slot.group is None)
        self.optional = frozenset(self.names) - self.required
        # Every key a successful parse of this template can produce.
        self.produced: tuple[str, ...] = (
            *((ROOT,) if self.has_root else ()),
            *dict.fromkeys(self.names),
            *self.composites,
        )
        self._owner: dict[str, str | None] = {}
        for slot in self.slots:
            self._owner.setdefault(slot.name, slot.composite)
        punctuation = {
            character
            for piece in self._pieces
            if isinstance(piece, str)
            for character in piece
            if not character.isalnum()
        }
        self.delimiters = frozenset(punctuation | PATH_SEPARATORS)
        # One matcher, two attempts. The precise pattern pastes each field's own rule into its
        # slot, so a value may contain the template's punctuation when its rule allows it, and
        # a correct name reads exactly as one regex built from the rules would. It is the only
        # attempt a correct name needs. The fallback lets each slot take its rule or, failing
        # that, any punctuation-free chunk; it runs only when the precise one fails, so that the
        # wrong piece still lands in its slot and gets a field-level diagnostic.
        allowed = "[^" + re.escape("".join(sorted(self.delimiters))) + "]*"
        precise: list[str] = []
        loose: list[str] = []
        if self.has_root:
            prefixes = sorted(self.roots.values(), key=len, reverse=True)
            root = "(?P<root>" + "|".join(map(re.escape, prefixes)) + ")"
            precise.append(root)
            loose.append(root)
        index = 0
        for piece in self._pieces:
            if isinstance(piece, str):
                precise.append(re.escape(piece))
                loose.append(re.escape(piece))
            elif isinstance(piece, GroupStart):
                precise.append("(?:")
                loose.append("(?:")
            elif isinstance(piece, GroupEnd):
                precise.append(")?")
                loose.append(")?")
            else:
                spec = fields[piece.name]
                rule = slot_pattern(spec)
                precise.append(f"(?P<f{index}>(?:{rule}))")
                # A rule that stays inside the punctuation is covered by the chunk already;
                # only a rule that can cross it needs its own branch (and the backtracking).
                if may_contain(spec, self.delimiters):
                    loose.append(f"(?P<f{index}>(?:{rule}|{allowed}))")
                else:
                    loose.append(f"(?P<f{index}>{allowed})")
                index += 1
        self.regex = re.compile("".join(precise))
        self.fallback_regex = re.compile("".join(loose))
        # A composite's joined value is its own template rendered from the parts.
        self._composite_templates = {
            name: Template(fields[name].template, fields) for name in self.composites
        }

    def _expand(self, text: str, composite: str | None, chain: tuple[str, ...]) -> None:
        for segment, optional in split_groups(text):
            if not optional:
                self._expand_parts(parse_parts(segment), composite, chain)
                continue
            if self._group is not None:
                fail("invalid_template", f"Optional groups cannot nest in {self.text!r}.")
            group = Group(len(self.groups))
            self.groups.append(group)
            self._pieces.append(GroupStart(group.index))
            before = self._separated
            first_piece, first_slot = len(self._pieces), len(self.slots)
            self._group = group.index
            self._expand_parts(parse_parts(segment), composite, chain)
            self._group = None
            group.names = tuple(dict.fromkeys(slot.name for slot in self.slots[first_slot:]))
            inner = self._pieces[first_piece:]
            if not group.names:
                fail("invalid_template", "An optional group needs at least one field.")
            edges = (inner[0], inner[-1])
            if not any(isinstance(edge, str) and has_punctuation(edge) for edge in edges):
                fail(
                    "ambiguous_template",
                    "An optional group must start or end with literal punctuation.",
                )
            self._pieces.append(GroupEnd(group.index))
            # When the group is absent, whatever preceded it meets whatever follows it.
            self._separated = before and self._separated

    def _expand_parts(
        self, parts: list[tuple], composite: str | None, chain: tuple[str, ...]
    ) -> None:
        for literal, name, formatting, conversion in parts:
            if literal:
                self._pieces.append(literal)
                self._separated = self._separated or has_punctuation(literal)
            if name is None:
                continue
            if formatting or conversion:
                fail("invalid_template", "Put formatting rules in field definitions.")
            if name == ROOT:
                if self.roots is None:
                    fail("invalid_template", "{root} is only available in a location.")
                if not self.roots:
                    fail("missing_root", "Declare roots before using {root} in a location.")
                if self.has_root or self._pieces or self._group is not None:
                    fail("invalid_template", "{root} must start the location and appear once.")
                self.has_root = True
                self._separated = False
                continue
            spec = self.fields.get(name)
            if spec is None:
                fail("unknown_field", f"Unknown field {name!r} in {self.text!r}.")
            if spec.kind == "composite":
                if name in chain:
                    fail("cyclic_field", f"Composite field {name!r} refers to itself.", field=name)
                start = len(self.slots)
                self._expand(spec.template, name, (*chain, name))
                leaves = self._leaves_of.setdefault(name, set())
                leaves.update(slot.name for slot in self.slots[start:])
                if name not in self.composites:
                    self.composites.append(name)
                continue
            if not self._separated:
                fail("ambiguous_template", "Separate fields with literal punctuation.")
            self._separated = False
            slot = Slot(name, composite, self._group)
            self._pieces.append(slot)
            self.slots.append(slot)

    def validate(self, text: str, resource: str, source: str = "name") -> Validation:
        match = self.regex.fullmatch(text) or self.fallback_regex.fullmatch(text)
        if not match:
            return Validation(
                resource,
                text,
                {},
                (
                    Diagnostic(
                        "pattern_mismatch",
                        "Input does not fit the template structure.",
                        expected=self.text,
                        actual=text,
                    ),
                ),
                source,
            )
        values: dict[str, str | int] = {}
        diagnostics: list[Diagnostic] = []
        raw_values: dict[str, str] = {}
        spans: dict[str, tuple[int, int]] = {}
        presence: dict[str, set[bool]] = {}
        conflicts: set[str] = set()
        if self.has_root:
            values[ROOT] = match[ROOT]
        for index, slot in enumerate(self.slots):
            raw = match[f"f{index}"]
            presence.setdefault(slot.name, set()).add(raw is not None)
            if raw is None:
                continue
            span = match.span(f"f{index}")
            if slot.name in raw_values and raw != raw_values[slot.name]:
                conflicts.add(slot.name)
                diagnostics.append(
                    Diagnostic(
                        "conflicting_field",
                        f"Repeated {slot.name!r} values disagree.",
                        slot.name,
                        raw_values[slot.name],
                        raw,
                        span,
                        slot.composite,
                    )
                )
            raw_values.setdefault(slot.name, raw)
            spans.setdefault(slot.name, span)
            try:
                values[slot.name] = field_value(self.fields[slot.name], raw, parsing=True)
            except NameSpecError as exc:
                diagnostics.extend(
                    replace(item, span=span, composite=slot.composite) for item in exc.diagnostics
                )
                conflicts.add(slot.name)
        for name, seen in presence.items():
            if len(seen) > 1:
                conflicts.add(name)
                diagnostics.append(
                    Diagnostic(
                        "conflicting_field",
                        f"{name!r} is present in one place and absent in another.",
                        name,
                        None,
                        raw_values.get(name),
                        spans.get(name),
                        self._owner.get(name),
                    )
                )
        for name in conflicts:
            values.pop(name, None)
        for name in self.composites:
            try:
                values[name] = self._composite_templates[name].format(values)
            except NameSpecError:
                pass  # A part is missing, invalid or conflicting; the whole is omitted too.
        return Validation(resource, text, values, tuple(diagnostics), source)

    def format(self, values: Mapping[str, Any]) -> str:
        working = dict(values)
        rendered: dict[str, str] = {}
        diagnostics: list[Diagnostic] = []
        explained: set[str] = set()
        # Outer composites first, so a whole Shot supplies Sequence before Sequence is checked.
        for name in reversed(self.composites):
            value = working.get(name)
            if value is None:
                continue
            try:
                parts = self._composite_value(name, value)
            except NameSpecError as exc:
                diagnostics.extend(exc.diagnostics)
                # The parts are missing because the whole value was bad; one report is enough.
                explained.update(self._leaves_of[name])
                continue
            for part, part_value in parts.items():
                given = working.get(part)
                if given is None:
                    working[part] = part_value
                elif given != part_value or type(given) is not type(part_value):
                    diagnostics.append(
                        Diagnostic(
                            "conflicting_field",
                            f"{part!r} disagrees with the value given for {name!r}.",
                            part,
                            part_value,
                            given,
                            composite=name,
                        )
                    )
        if self.has_root:
            try:
                rendered[ROOT] = self._root_value(working.get(ROOT))
            except NameSpecError as exc:
                diagnostics.extend(exc.diagnostics)
        # A group renders when any of its fields is supplied; the rest of them are then required.
        present = {
            group.index
            for group in self.groups
            if any(working.get(name) is not None for name in group.names)
        }
        wanted = set(self.required)
        for group in self.groups:
            if group.index in present:
                wanted.update(group.names)
        for name in dict.fromkeys(self.names):
            spec = self.fields[name]
            if working.get(name) is None and (name in explained or name not in wanted):
                continue
            try:
                text = spelling(spec, field_value(spec, working.get(name), parsing=False))
                if any(character in PATH_SEPARATORS for character in text):
                    fail(
                        "reserved_separator",
                        f"{name!r} contains a path separator.",
                        field=name,
                        actual=text,
                    )
                rendered[name] = text
            except NameSpecError as exc:
                owner = self._owner.get(name)
                diagnostics.extend(
                    replace(item, composite=owner) if item.composite is None else item
                    for item in exc.diagnostics
                )
        if diagnostics:
            raise NameSpecError(diagnostics)
        output = [rendered[ROOT]] if self.has_root else []
        skipping = False
        for piece in self._pieces:
            if isinstance(piece, GroupStart):
                skipping = piece.index not in present
            elif isinstance(piece, GroupEnd):
                skipping = False
            elif not skipping:
                output.append(piece if isinstance(piece, str) else rendered[piece.name])
        return "".join(output)

    def _composite_value(self, name: str, value: Any) -> dict[str, str | int]:
        template = self.fields[name].template
        if not isinstance(value, str):
            fail("invalid_type", f"{name!r} requires text.", field=name, actual=value)
        result = self._composite_templates[name].validate(value, name)
        if not result.valid:
            fail(
                "invalid_field",
                f"{name!r} does not fit {template!r}.",
                field=name,
                expected=template,
                actual=value,
            )
        return result.fields

    def _root_value(self, value: Any) -> str:
        if value is None or value == "":
            fail("missing_field", "Missing 'root'.", field=ROOT, actual=value)
        if not isinstance(value, str):
            fail("invalid_type", "'root' requires text.", field=ROOT, actual=value)
        if value in self.roots:
            return self.roots[value]
        if value in self.roots.values():
            return value
        fail(
            "invalid_field",
            "'root' must be a declared root name or value.",
            field=ROOT,
            expected=sorted(self.roots),
            actual=value,
        )
