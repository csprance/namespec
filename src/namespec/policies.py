"""Optional filesystem checks, separate from a convention's naming rules.

pathvalidate owns platform filename restrictions. This adapter retains input spans and
rejects traversal components before normalization can hide them. It does not touch disk.
"""

from __future__ import annotations

import re
from typing import Any

from .models import Diagnostic, fail

PLATFORMS = {"posix": "POSIX", "windows": "Windows", "portable": "universal"}


def _validator() -> Any:
    try:
        import pathvalidate
    except ImportError:
        fail(
            "unavailable_filesystem_policy",
            "Filesystem policies require the namespec[filesystem] extra.",
        )
    return pathvalidate


def check_filesystem_policy(policy: str | None) -> None:
    if policy is not None:
        if policy not in PLATFORMS:
            raise ValueError("filesystem must be None, 'posix', 'windows', or 'portable'")
        _validator()


def filesystem_diagnostics(
    text: str, policy: str | None, *, source: str = "name"
) -> tuple[Diagnostic, ...]:
    """Check components without resolving paths or changing the original text."""
    if policy is None:
        return ()
    check_filesystem_policy(policy)
    validator = _validator()
    # Drive letters are a path prefix, not a filename containing a colon. Backslashes
    # are separators only under Windows/portable policies; POSIX keeps them literal.
    start = 0
    if source == "location" and policy != "posix" and re.match(r"[A-Za-z]:[/\\]", text):
        start = 2
    pattern = r"[^/\\]+" if policy != "posix" else r"[^/]+"
    components = (
        [(text, 0, len(text))]
        if source != "location"
        else [
            (m.group(), m.start(), m.end())
            for m in re.finditer(pattern, text)
            if m.start() >= start
        ]
    )
    diagnostics = []
    for component, begin, end in components:
        reason = None
        if component in {".", ".."}:
            reason = "Traversal components are not allowed."
        elif any(ord(character) < 32 or ord(character) == 127 for character in component):
            reason = "Control characters are not allowed."
        else:
            try:
                validator.validate_filename(
                    component, platform=PLATFORMS[policy], fs_encoding="utf-8"
                )
            except validator.ValidationError as exc:
                reason = str(exc)
            except UnicodeError:
                reason = "The component cannot be encoded as UTF-8."
        if reason:
            diagnostics.append(
                Diagnostic(
                    "unsafe_path", reason, expected=policy, actual=component, span=(begin, end)
                )
            )
    return tuple(diagnostics)
