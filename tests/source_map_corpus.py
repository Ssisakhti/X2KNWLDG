"""A project whose Source Map actually has something in it (`T-254`).

Three record families feed the two source-graph endpoints, and a corpus that
exercises them has to carry all three: a source node per run (every run has
one), a readable brief (only some runs have one), and at least one accepted
cross-source relation (a corpus can honestly have none).

``tests/fixtures/source-map/valid/`` already holds exactly that set, generated
by ``build_fixtures.py`` from the committed runs' own bytes — real unit ids and
real input digests, through ``x2knwldg.synthesis``. So this module does not
write a brief or a relation of its own: it copies the runs those documents were
built against and puts the documents where the pipeline would have written
them. A brief invented here would carry a digest of nothing and would report
``stale`` the moment anything read it, which is the opposite of what a fixture
for the *available* state is for.

The corpus is deliberately uneven, because every state has to be reachable:

* ``pass-run`` — an ``available`` brief, and one endpoint of the relation;
* ``twitter-runs/quote`` — an ``available`` brief over the other medium, and
  the other endpoint;
* ``partial-run`` — an ``available`` brief whose ``status`` is ``PARTIAL``,
  because a brief may not claim more than its run;
* ``fail-run`` — **no** brief at all, which is the ``unavailable`` state and is
  a normal, possibly permanent condition rather than a shortfall (D-257).

Nothing here is written into ``tests/fixtures/``: the runs are copied, exactly
as every other harness in this suite copies them, because ``raw/`` is immutable
evidence. Stdlib only, so the zero-dependency CI job can use it.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_RUNS = PROJECT_ROOT / "tests" / "fixtures" / "runs"
TWITTER_RUNS = PROJECT_ROOT / "tests" / "fixtures" / "twitter-runs"
SOURCE_MAP = PROJECT_ROOT / "tests" / "fixtures" / "source-map" / "valid"

#: ``(fixture directory, directory name in the project, brief fixture or None)``.
#: The brief filenames are the ones ``build_fixtures.py`` writes, and each names
#: in its own ``source_id`` the run it was built from.
LAYOUT: tuple[tuple[Path, str, str | None], ...] = (
    (FIXTURE_RUNS / "pass-run", "pass-run", "youtube-source_knowledge.json"),
    (FIXTURE_RUNS / "partial-run", "partial-run", "partial-source_knowledge.json"),
    (FIXTURE_RUNS / "fail-run", "fail-run", None),
    (TWITTER_RUNS / "quote", "twitter-quote", "twitter-source_knowledge.json"),
)

#: The source ids the four runs declare. Their directory names deliberately
#: differ from them — ``pass-run/`` declares ``fixture-pass`` — so nothing may
#: assume the two match.
YOUTUBE_PASS = "youtube:fixture-pass"
YOUTUBE_PARTIAL = "youtube:fixture-partial"
YOUTUBE_FAIL = "youtube:fixture-fail"
TWITTER_QUOTE = "twitter:2094039408081068233"

#: The one relation ``valid/synthesis/source_relations.json`` holds, and its
#: two endpoints. Named here so a test asserts against the fixture's own id
#: rather than recomputing one and agreeing with itself.
RELATION_ID = "SR-f596992c42435c40"
RELATION_FROM = TWITTER_QUOTE
RELATION_TO = YOUTUBE_PASS

#: Every source the corpus holds, in the order ``global_id`` sorts them.
SOURCE_IDS = (TWITTER_QUOTE, YOUTUBE_FAIL, YOUTUBE_PARTIAL, YOUTUBE_PASS)

#: A well-formed source id no run in the corpus declares.
UNKNOWN_SOURCE = "youtube:never-ingested"


@dataclass(frozen=True)
class Corpus:
    """A project root, and what is true about it."""

    project_root: Path

    @property
    def output(self) -> Path:
        return self.project_root / "output"


def build(root: Path, *, relations: bool = True, library: bool = True) -> Corpus:
    """The corpus under *root*.

    *relations* false leaves ``output/synthesis/`` absent, which is the honest
    state of every project that has never run source synthesis and the one a
    "no relation" assertion has to be made against.
    """
    from x2knwldg.library import rebuild_library

    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)
    for fixture, name, brief in LAYOUT:
        destination = output / name
        shutil.copytree(fixture, destination)
        if brief is not None:
            shutil.copy2(SOURCE_MAP / brief, destination / "source_knowledge.json")
    if relations:
        synthesis = output / "synthesis"
        synthesis.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            SOURCE_MAP / "synthesis" / "source_relations.json",
            synthesis / "source_relations.json",
        )
    if library:
        rebuild_library(output)
    return Corpus(project_root=root)
