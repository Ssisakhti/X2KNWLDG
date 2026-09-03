"""Capture shapes that no measured route produces, constructed for tests (T-227).

Every capture under ``tests/fixtures/captures/`` is a claim about what a
provider returned: that directory's README opens by declaring each fixture
derived from "the bytes a real acquisition returned", and
``test_a_capture_can_be_revalidated_from_raw_evidence`` enforces it over every
file in it. So a shape that was never measured cannot live there — a committed
capture asserting the pinned provider returned something it never returned is
the class of lie the ``sha256_raw``/``sha256_sanitized`` pair exists to prevent
(D-222).

It cannot be labelled its way out of that, either. The capture schema's root is
``additionalProperties: false``, so the ``"fixture": true`` marker the run
fixtures carry has nowhere to go, and ``network.note`` and ``order.note`` are
about the network and the ordering rather than the document's provenance.

What is left is this: build the shape **in the test process**, from a committed
capture, so nothing on disk claims to be evidence. That is how the twelve-entry
rejection catalogue in ``tests/test_twitter_capture.py`` already works. This
module is separate from ``twitter_harness.py`` on purpose — that harness
promises, in its own docstring, that "what it replays is committed evidence, not
invented JSON", and an edit history is exactly invented JSON.

Why an edit history has to be invented at all: the ``T-222`` spike scanned 610
credential-free posts across seven accounts and found no edited post, and
``x fields tweet`` declares ``edits`` with **no surface at any tier**
([REPORT.md](../docs/spikes/T-222/REPORT.md) §9). Search, which is how one would
hunt for an instance directly, is Tier 2 and excluded by ADR 0007. The report's
instruction for this phase is that ``T-227`` "must treat all four as
absent-unless-represented, never as fields to guess" — so what is pinned here is
not a measurement but a *decision about handling*, taken now while there is no
live data to improvise against.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "captures"

#: Prior version ids for the constructed edit history, oldest first.
#:
#: Deliberately in the same obviously-unreal range as
#: ``fail-unavailable-post``'s ``999999999999999999``, whose sibling was measured
#: as not-found on all three routes. A constructed shape should be legible as
#: constructed *in the data*, not only in a docstring: any id is syntactically a
#: post id, so picking plausible-looking ones would quietly assert something
#: about two real posts.
EDIT_PRIOR_IDS = ("999999999999999001", "999999999999999002")


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def edited_post_capture(base: str = "pass-single-post-en") -> dict[str, Any]:
    """A committed capture, plus an edit history on its single item.

    **What ``edits`` means**, which the schema does not say and no measurement
    could settle (D-224): the ids of the post's *prior* versions, oldest first,
    and never the item's own id. X's own ``edit_history_tweet_ids`` includes the
    current version, so a provider adapter has to drop it — and the reason to
    define the field this way is that it makes one sentence true without
    exception: **nothing named in ``edits`` was observed.** Include the current
    id and that sentence needs a carve-out for the one id that *was*, which is
    the kind of qualifier a reader stops applying.

    Everything else about the prior versions is absent, because absent is what
    was observed: no text, no timestamp, no author. The capture says a post was
    edited and names the versions; it does not say what they contained.

    Coverage is untouched, and that is the deliberate part. A prior version is
    not another post in the conversation — it is the same post in a state that
    no longer exists — so it is not an expected item, does not enter
    ``expected_item_count``, and cannot make an otherwise-``PASS`` capture
    ``PARTIAL``. The honest statement about it is ``edits`` itself.
    """
    capture = copy.deepcopy(_load(base))
    assert len(capture["items"]) == 1, f"{base} is not a single-item capture"
    capture["items"][0]["edits"] = list(EDIT_PRIOR_IDS)
    return capture
