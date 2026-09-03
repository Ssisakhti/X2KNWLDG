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


# --------------------------------------------------------------------------
# D-096 — the "measured from disk" table is measured, not remembered
# --------------------------------------------------------------------------
#
# §3 of `docs/PROJECT_MANAGEMENT.md` states counts read off the filesystem, and
# an external audit found four of its rows stale at once: 1263 lines / 398
# tests / seven API test files (against 1457 / 600 / eleven), 50 files / ~6.2k
# lines / 125 tests in 14 files for the frontend, and `T-008: ui is a refusing
# stub` for a command `T-116` had shipped. Its header said "Measured from disk
# on 2026-08-31" while carrying rows dated later, so freshness could not be
# read off it either.
#
# Line counts and test totals move on almost every commit and are left to §7.3.
# What is asserted here is the countable structure that drifts *silently*: how
# many files there are. A row that disagrees with the filesystem is this table
# being stale, never the measurement.

BOARD = PROJECT_ROOT / "docs" / "PROJECT_MANAGEMENT.md"


def test_the_api_test_file_count_is_the_one_on_disk() -> None:
    # The row spells the count as a word, so read it back the same way.
    words = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
        "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    }
    found = re.search(
        r"\*\*\d+ tests\*\* across (\w+) `tests/test_api_\*\.py` files",
        BOARD.read_text(encoding="utf-8"),
    )
    assert found is not None
    assert found.group(1) in words, f"spell the count as a word: {found.group(1)!r}"
    actual = len(list((PROJECT_ROOT / "tests").glob("test_api_*.py")))
    assert words[found.group(1)] == actual, (
        f"§3 says {found.group(1)} API test files; there are {actual}"
    )


def test_the_frontend_file_counts_are_the_ones_on_disk() -> None:
    text = BOARD.read_text(encoding="utf-8")
    found = re.search(
        r"\*\*(\d+) files / (\d+) lines\*\* under `web/src/`, \*\*\d+ tests\*\* in (\d+) files",
        text,
    )
    assert found is not None, "the frontend row's shape changed; update this guard"
    stated_files, _stated_lines, stated_test_files = (int(group) for group in found.groups())

    sources = [
        path
        for path in (PROJECT_ROOT / "web" / "src").rglob("*")
        if path.is_file() and path.suffix in {".ts", ".tsx", ".css"}
    ]
    test_files = [path for path in sources if path.name.endswith((".test.ts", ".test.tsx"))]
    assert stated_files == len(sources), f"§3 says {stated_files} files; there are {len(sources)}"
    assert stated_test_files == len(test_files), (
        f"§3 says {stated_test_files} frontend test files; there are {len(test_files)}"
    )


def test_no_document_still_calls_the_ui_command_a_stub() -> None:
    """`T-116` shipped it; four documents went on saying otherwise."""
    offenders: list[str] = []
    for path in sorted(PROJECT_ROOT.rglob("*.md")):
        if any(part in {"node_modules", "build", ".venv", "dist"} for part in path.parts):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "refusing stub" not in line:
                continue
            # A row that *records* that it used to be one is history, not a
            # claim about the present.
            if any(marker in line for marker in ("T-116", "~~", "used to", "left a")):
                continue
            offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{number}")
    assert not offenders, (
        "these still describe `x2knwldg ui` as a refusing stub: " + ", ".join(offenders)
    )


def test_the_boards_measurement_date_is_not_older_than_its_rows() -> None:
    """The header said 2026-08-31 while carrying rows dated 2026-09-02."""
    text = BOARD.read_text(encoding="utf-8")
    header = re.search(r"Measured from disk on \*\*(\d{4}-\d{2}-\d{2})\*\*", text)
    assert header is not None, "§3 no longer says when it was measured"
    dates = sorted(set(re.findall(r"\b(20\d{2}-\d{2}-\d{2})\b", text)))
    assert dates, "no dates in the board at all"
    assert header.group(1) >= max(dates), (
        f"§3 claims it was measured on {header.group(1)} but carries rows dated {max(dates)}"
    )


# ---------------------------------------------------------------------------
# Counted claims (D-187)
# ---------------------------------------------------------------------------
#
# `test_no_documentation_cites_a_line_number` enforces that a document cites a
# *symbol* rather than a line, on the argument that "a symbol name fails loudly
# -- `grep` returns nothing". Nothing in the repository ran that grep, so every
# semantic claim was unguarded and four of them had rotted: CI described as
# "five jobs" when there are nine, "the two FTS5 tables" when there is one,
# "every frozen endpoint now has a caller" when one has none, and a constant
# quoted as 12 that had been lowered to 4 in its own file. These are the cheap,
# mechanical ones -- each is a number that can be counted from the source it is
# about.


def _read(relative: str) -> str:
    return (PROJECT_ROOT / relative).read_text(encoding="utf-8")


def test_the_ci_job_count_is_the_one_in_the_workflow() -> None:
    import re as _re

    workflow = _read(".github/workflows/ci.yml")
    # Only inside the `jobs:` block: `on:` has two-space keys of its own, and
    # counting `push` and `pull_request` as jobs would make this guard wrong in
    # the same way as the claim it checks.
    assert "\njobs:\n" in workflow
    block = workflow.split("\njobs:\n", 1)[1]
    # A job id: two spaces, a name, a colon, nothing else on the line.
    jobs = _re.findall(r"^  ([a-z][\w-]*):$", block, _re.MULTILINE)
    assert len(jobs) >= 5, jobs
    text = _read("docs/PROJECT_MANAGEMENT.md")
    stated = _re.search(r"across \*\*(\w+)\s+jobs\*\*", text)
    assert stated is not None, "§7.2 no longer states a job count in the shape this reads"
    word = stated.group(1).strip()
    words = {
        "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    }
    assert words.get(word) == len(jobs), f"§7.2 says {word}; the workflow defines {len(jobs)}: {jobs}"


def test_the_fts5_table_count_is_the_one_in_the_schema() -> None:
    import re as _re

    schema = _read("src/x2knwldg/index/schema.py")
    # The probe table is created and dropped inside `connect`; it is not part of
    # the stored schema and must not be counted as one.
    created = [
        name
        for name in _re.findall(r"CREATE VIRTUAL TABLE (?:IF NOT EXISTS )?(\S+) USING fts5", schema)
        if "probe" not in name
    ]
    assert len(created) == 1, created
    readme = _read("src/x2knwldg/index/README.md")
    assert "The two FTS5 tables" not in readme, "there is one, and it is named"
    assert created[0].split(".")[-1] in readme


def test_the_map_label_budget_in_the_docs_is_the_one_in_the_source() -> None:
    import re as _re

    source = _read("web/src/map/labelPolicy.ts")
    found = _re.search(r"MAP_LABEL_NEIGHBOUR_BUDGET = (\d+)", source)
    assert found is not None, "the constant was renamed; update this guard"
    value = found.group(1)
    for relative in ("web/src/map/README.md", "web/src/map/constellation.ts"):
        text = _read(relative)
        for quoted in _re.findall(r"MAP_LABEL_NEIGHBOUR_BUDGET`? \((\d+)\)", text):
            assert quoted == value, f"{relative} quotes {quoted}; it is {value}"


def test_the_map_label_settings_in_the_docs_are_the_ones_in_the_source() -> None:
    """``web/src/map/README.md`` stated three retired numbers.

    It said one label per 180x180 px cell for nodes at least 14 px across, and
    eight labels over 86 marks. The settings are 560 and 6, and ``T-216``
    re-measured ten — three numbers a reader would have taken from the spec.
    ``labelPolicy.ts`` states them once; this is what keeps the prose quoting
    it rather than remembering it.
    """
    import re as _re

    source = _read("web/src/map/labelPolicy.ts")
    readme = _read("web/src/map/README.md")
    # The settings *object*, not a prose mention of a retired value: the
    # docstring above it discusses `labelGridCellSize: 180` as history, which
    # is exactly the number this guard exists to keep out of the README.
    settings = _re.search(
        r"MAP_LABEL_SETTINGS = \{(.*?)\} as const;", source, _re.DOTALL
    )
    assert settings is not None, "MAP_LABEL_SETTINGS was renamed; update this guard"

    for setting in ("labelGridCellSize", "labelRenderedSizeThreshold"):
        found = _re.search(rf"{setting}: (\d+)", settings.group(1))
        assert found is not None, f"{setting} was renamed; update this guard"
        value = found.group(1)
        # Whatever number the prose puts beside the rule has to be this one.
        quoted = {
            match
            for match in _re.findall(
                r"one label per \*\*(\d+)x\d+ px\*\*"
                if setting == "labelGridCellSize"
                else r"least \*\*(\d+) px\*\*",
                readme.replace("×", "x"),
            )
        }
        assert quoted == {value}, (
            f"web/src/map/README.md quotes {sorted(quoted)} for {setting}; it is {value}"
        )

    # And the measured label count, which the source states twice and the
    # README once.
    measured = set(_re.findall(r"\*\*(\w+) labels over 86\s+marks\*\*", source))
    assert len(measured) == 1, f"labelPolicy.ts states {sorted(measured)}"
    assert measured == set(
        _re.findall(r"\*\*(\w+) labels over 86\s+marks\*\*", readme)
    ), "the README's measured label count is not labelPolicy.ts's"


def test_the_measured_differences_the_docs_count_are_the_ones_in_the_spec() -> None:
    """D-203: five documents said "four measured differences in `SPEC.md` §17".

    §17 is where a difference from the approved compositions stands instead of
    being fixed, so its length is a number a reader takes from the docs and
    acts on — exactly the class of claim that made three of the map README's
    numbers wrong. D-203 added two items to it, and every pointer said four.
    """
    import re as _re

    spec = _read("docs/mockups/T-211/SPEC.md")
    section = spec.split("### The differences that remain, measured", 1)
    assert len(section) == 2, "§17's differences heading changed; update this guard"
    body = section[1].split("### Regenerating", 1)[0]
    items = _re.findall(r"^(\d+)\. \*\*", body, _re.MULTILINE)
    assert items, "§17 lists no numbered differences"
    counted = len(items)
    assert [int(number) for number in items] == list(range(1, counted + 1)), items

    words = {4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}
    for path in ("docs/PROJECT_MANAGEMENT.md", "docs/KNOWLEDGE_CANVAS_PLAN.md"):
        text = _read(path)
        for quoted in _re.findall(r"(\w+) measured differences", text):
            # A sentence may say what `T-216` left *and* name the current
            # total; what it may not do is name a total that is not one.
            assert quoted in words.values(), f"{path}: {quoted!r} is not a count"
            if words.get(counted) == quoted:
                continue
            # Any other number has to be scoped to the task that left it, and
            # to say where the rest are.
            assert words[counted] in text, (
                f"{path} says {quoted!r} measured differences and never mentions the "
                f"current {words[counted]}; §17 now lists {counted}"
            )


def test_the_endpoint_caller_claim_is_the_census_on_disk() -> None:
    """"Every frozen endpoint has a caller" was true of ten of eleven."""
    import json as _json
    import re as _re

    spec = _json.loads(_read("schemas/api/v1/openapi.json"))
    operations = {
        operation["operationId"]
        for path in spec["paths"].values()
        for operation in path.values()
    }
    # An operation the client wraps is called through the wrapper's name, not
    # through its own: `getArtifactMedia` is reached as `api.media(...)` and
    # `api.mediaUrl(...)`. Read the wrappers out of `client.ts` rather than
    # assuming a naming convention, so a renamed wrapper fails here loudly.
    client = _read("web/src/api/client.ts")
    wrappers: dict[str, set[str]] = {}
    for method, operation in _re.findall(
        r"(?:async )?(\w+)\([^)]*\)[^{]*\{(?:[^{}]|\{[^{}]*\})*?\"(\w+)\"", client
    ):
        if operation in operations:
            wrappers.setdefault(operation, set()).add(method)

    web = PROJECT_ROOT / "web" / "src"
    callers = set()
    for module in web.rglob("*.ts*"):
        if module.name.endswith((".test.ts", ".test.tsx")) or module.name == "client.ts":
            continue
        text = module.read_text(encoding="utf-8")
        for name in operations:
            names = {name} | wrappers.get(name, set())
            if any(_re.search(rf"\b{spelling}\b", text) for spelling in names):
                callers.add(name)
    uncalled = sorted(operations - callers)
    readme = _read("web/README.md")
    if uncalled:
        assert "Every frozen endpoint now has a caller" not in readme, (
            f"web/README.md claims every endpoint has a caller; these do not: {uncalled}"
        )
        for name in uncalled:
            assert name in readme, f"{name} has no caller and web/README.md does not say so"
    else:
        assert "have a caller" in readme
