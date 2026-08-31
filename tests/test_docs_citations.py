"""The citation convention, enforced instead of hoped for.

The Phase 0 audit found roughly 3 in 5 ``file:line`` pointers across the docs
already stale after a single session, and named the convention itself as the
liability rather than any individual pointer. Three more went stale while the
audit's own findings were being fixed, one of them *during* the session.

A line number rots silently: the file still exists, the line still exists, and
the reader is sent somewhere plausible and wrong. A symbol name fails loudly —
``grep`` returns nothing — so a stale citation announces itself. That asymmetry
is the whole argument, and this test is what makes it a rule.

A citation that is *about* a rotted line number is legitimate history: ADR 0003
exists partly because ``pipeline.py:42`` had become a blank line, and quoting
it is the point. Those lines carry ``<!-- citation:history -->``.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: ``path/to/file.py:123`` or ``file.py:36-102``, anywhere in a line of prose.
CITATION = re.compile(r"[A-Za-z0-9_/.-]+\.(?:py|ts|json|yml|md):\d+(?:-\d+)?")

#: A line that quotes a citation as history, which is exactly what some of the
#: ADR text is for.
HISTORY_MARKER = "<!-- citation:history -->"

#: Directories that are not this project's prose: vendored, generated, or the
#: user's own canonical output.
SKIP = ("/.venv/", "/node_modules/", "/legacy/", "/vault/", "/inbox/", "/output/", "/build/", "/.git/")


def documentation_files() -> list[Path]:
    return sorted(
        path
        for path in PROJECT_ROOT.glob("**/*.md")
        if not any(part in f"/{path.relative_to(PROJECT_ROOT).as_posix()}" for part in SKIP)
    )


def test_no_documentation_cites_a_line_number() -> None:
    offenders: list[str] = []
    for path in documentation_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if HISTORY_MARKER in line:
                continue
            for match in CITATION.finditer(line):
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT)}:{number} cites {match.group(0)}"
                )
    assert not offenders, (
        "cite a symbol, not a line number — a symbol fails loudly when it moves:\n  "
        + "\n  ".join(offenders)
    )


def test_the_guard_can_actually_fail() -> None:
    """A rule nothing can violate is not a rule. This is the tautology check."""
    assert CITATION.search("`pipeline.py:42` is a blank line now")
    assert CITATION.search("see query.py:36-102 for the scan")
    assert not CITATION.search("`pipeline.resolve_run_dir` rejects it")
    assert not CITATION.search("ADR 0003 supersedes invariant 8")


def test_history_is_allowed_to_quote_a_rotted_citation() -> None:
    """The four ADR lines that exist *because* a line number rotted."""
    quoted = [
        (path, number, line)
        for path in documentation_files()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if HISTORY_MARKER in line
    ]
    assert quoted, "the marker exists for the ADRs that quote a rotted citation"
    for path, number, line in quoted:
        assert CITATION.search(line), (
            f"{path.relative_to(PROJECT_ROOT)}:{number} is marked as a historical "
            "citation but cites no line number — drop the marker"
        )
