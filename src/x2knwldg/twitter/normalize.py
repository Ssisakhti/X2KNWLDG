"""One x-cli record becomes one capture item. Provider shape stops here.

This is the boundary ADR 0007 decision 7 draws: extraction and the UI consume
the capture contract and never see a provider response. Everything below reads
an x-cli ``tweet`` record and copies out only what
``schemas/capture/v1/twitter_capture.schema.json`` can carry.

**These three functions were written for the** ``T-223`` **fixtures and moved
here unchanged.** They are the same normalization either way, and two copies of
"how a provider record becomes a capture" is two answers to that question the
moment one of them is edited. ``tests/fixtures/captures/build_captures.py`` now
imports them, and the byte-identical regeneration check that ``T-223`` already
requires is what proves the move was faithful: the eight committed captures
still rebuild to the same bytes.

Two measured decisions are encoded here rather than restated:

**Spans are codepoint offsets into the authored text** (D-211). T-222 proved the
facet indices are codepoints, not UTF-16 code units, against a post carrying
astral emoji where the UTF-16 reading came back shifted by two and mangled.
Python string slicing is natively codepoint-indexed, and every span is re-sliced
here against its own claimed text — a facet that does not slice back to itself
is dropped rather than trusted, so a provider change cannot quietly write a
wrong offset into a stored corpus.

**An absent field is absent, never empty.** ``media`` and ``edits`` carry
``minItems: 1`` in the contract and ``poll``/``article`` carry
``minProperties: 1``, because ``[]`` and ``{}`` would claim absence *was
observed* — which a surface that truncates silently cannot support. So a record
with no media produces a post with no ``media`` key at all.

**At the qualified local route, only mention spans are produced.** Measured
again live on 2026-09-04, and it is a limit of the route rather than of this
code: x-cli's ``entities.urls`` holds *expanded* URLs that appear nowhere in the
authored text, and one post of the NASA thread carried
``https://t.co/ZKTzQCAGxC https://t.co/IOuHw9MYwr`` in its text against the
single entry ``https://go.nasa.gov/4chzg9c``. A ``t.co`` link can therefore be
*located* in the text but cannot be *paired* with what it points at, and a span
whose target is guessed is worse than no span. Facets — which carry the triple
that makes the pairing safe — come from the opt-in route ``T-225`` owns, so a
capture from this seam carries mention spans and no URL spans. Absent, not wrong.

**Metrics are deliberately not carried.** The records hold them and the contract
can represent them, but only as an observation with an ``observed_at``. Copying
them here would put a like count into every capture, and a bare count invites
comparison across time as though it were a property of the post. ``T-227``
decides whether extraction wants them; acquisition does not need them.
"""

from __future__ import annotations

import re
from typing import Any


def _offsets(indices: Any, length: int) -> tuple[int, int] | None:
    """A facet's ``indices`` as a usable half-open span, or ``None``.

    Every rejection here was reachable and two of them were measured, because
    the guard below did ``text[start:end] != original`` on whatever the provider
    put in the list:

    * ``indices: [-5, -1]`` slices *from the end of the string*, so a facet
      claiming a negative offset re-sliced to its own ``original`` and passed —
      and then wrote ``"start_char": -5`` into the capture, which
      ``schemas/capture/v1/`` declares ``minimum: 0`` and which nothing applies
      at runtime. A negative index is not a span into this text; it is a
      different span into this text, silently.
    * ``indices: ["0", 3]`` and ``indices: [None, 3]`` raised a bare
      ``TypeError`` out of the slice, so one malformed facet took the whole
      acquisition down while the malformed facets *beside* it — a missing
      ``original``, a list of the wrong length — were dropped as designed. One
      shape of bad data, two behaviours.
    * a span running past the end of the text, or ending before it starts, is
      not a span either. Python slicing clamps both and would hand back a
      shorter string that could still equal a short ``original``.

    ``bool`` is refused with the other non-integers on purpose: ``True`` is an
    ``int`` in Python and ``text[True:3]`` is a legal slice, which is exactly
    the kind of accident this function exists to stop being silent.
    """
    if not isinstance(indices, list) or len(indices) != 2:
        return None
    start, end = indices
    for value in (start, end):
        if isinstance(value, bool) or not isinstance(value, int):
            return None
    if not 0 <= start <= end <= length:
        return None
    return start, end


def entities_from(text: str, facets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Spans into the authored text (D-211), taken from the provider's facets.

    Facets carry ``indices``/``original``/``replacement`` as a triple, so no link
    is paired with a target by inference. x-cli's own ``entities.urls`` cannot
    support that pairing: it holds expanded URLs that appear nowhere in the text,
    and one measured post had two ``t.co`` links against a single entry.

    Indices are codepoint offsets — proven against a post carrying astral emoji,
    where the UTF-16 reading is shifted and mangled. Every span is re-sliced here
    against :func:`_offsets`-validated bounds, and a facet that does not slice
    back to its own ``original`` is dropped rather than trusted, so a provider
    change cannot quietly write a wrong offset into a committed fixture.

    The bounds check is not decoration. Until
    ``tests/fixtures/twitter-runs/facets/`` existed, **no committed fixture
    carried a facet at all** — the five ``__xcli_guest`` spike files report
    ``facets: 0`` — so this loop body had zero test execution while its own
    docstring said the guard had been "proven against a post carrying astral
    emoji". It had never run. That fixture is what runs it.

    **Stated plainly, because it is easy to misread this function's status:**
    no *acquisition* call site passes facets today. ``acquire._assemble`` calls
    :func:`post_from` with three arguments, so the qualified local route
    produces mention spans and nothing else — which is the measured limit of
    that route (D-218), not a gap here. The callers that do pass facets are the
    two fixture builders and the corroborating route ``T-225`` will add. The
    function is therefore live code on a path this project already exercises and
    already commits the output of, and it is kept rather than gated because
    deleting the guard would mean re-deriving it under ``T-225`` — at which
    point it would be new, untested code standing between a provider's offsets
    and a stored corpus.
    """
    out: list[dict[str, Any]] = []
    for facet in facets:
        original = facet.get("original")
        if not isinstance(original, str) or not original:
            continue
        offsets = _offsets(facet.get("indices"), len(text))
        if offsets is None:
            continue
        start, end = offsets
        if text[start:end] != original:
            continue
        kind = "url" if facet.get("type") in {"url", "media"} else facet.get("type")
        if kind not in {"url", "mention", "hashtag", "cashtag"}:
            continue
        entity: dict[str, Any] = {
            "kind": kind,
            "start_char": start,
            "end_char": end,
            "shortened": original,
        }
        replacement = facet.get("replacement")
        if replacement and replacement != original:
            entity["expanded"] = replacement
        out.append(entity)
    return sorted(out, key=lambda e: e["start_char"])


#: What may follow a handle and still end it. X allows ``[A-Za-z0-9_]`` in a
#: handle, so anything outside that set is a boundary — punctuation, whitespace,
#: an emoji, RTL text, or the end of the post.
_HANDLE_CHARS = re.compile(r"[A-Za-z0-9_]")


def mentions_from(text: str, record: dict[str, Any]) -> list[dict[str, Any]]:
    """Mention spans, located in the authored text by the handle itself.

    x-cli lists mentions as bare handles with no offsets, so the span is found
    rather than read. Only an unambiguous single occurrence is recorded; a handle
    appearing twice is left out rather than guessed at.

    "Unambiguous" has to include the **right-hand boundary**, and it did not.
    ``text.find("@" + handle)`` matches a prefix, and the occurrence count is
    taken over the same prefix, so a post reading
    ``@NASARoman is getting ready…`` against ``entities.mentions == ["NASA",
    "NASARoman"]`` — one post mentioning one account whose handle contains
    another's — produced a mention span claiming ``@NASA`` at characters 0–5.
    That span is a *false citation about authored text*, and nothing downstream
    catches it: ``extract._rederivation_errors`` excludes entities from the
    comparison by design (a corroborated capture carries spans one response
    cannot supply), so the wrong offsets would have survived every ``validate``
    the run ever ran.

    So the match must end where the handle ends. Both the location and the
    ambiguity test use the bounded form, because counting one way and locating
    the other is how the two came to disagree in the first place.
    """
    out: list[dict[str, Any]] = []
    for handle in (record.get("entities") or {}).get("mentions") or []:
        if not isinstance(handle, str) or not handle:
            continue
        needle = f"@{handle}"
        starts = [
            index
            for index in _occurrences(text, needle)
            # A handle is over when the next character cannot be part of one.
            # End of string counts, which is why the slice is taken rather than
            # the character indexed.
            if not _HANDLE_CHARS.match(text[index + len(needle) : index + len(needle) + 1])
        ]
        if len(starts) != 1:
            continue
        first = starts[0]
        out.append(
            {
                "kind": "mention",
                "start_char": first,
                "end_char": first + len(needle),
                "handle": handle,
            }
        )
    return out


def _occurrences(text: str, needle: str) -> list[int]:
    """Every start index of *needle* in *text*, overlaps included."""
    found: list[int] = []
    index = text.find(needle)
    while index >= 0:
        found.append(index)
        index = text.find(needle, index + 1)
    return found


def post_from(
    record: dict[str, Any],
    supplied_by: dict[str, Any],
    completeness: dict[str, Any],
    facets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One available post, as the capture contract represents it."""
    text = record.get("text") or ""
    author = record.get("author") or {}
    post: dict[str, Any] = {
        "post_id": record["id"],
        "author": {"username": author["username"], "rest_id": author["rest_id"]},
        "availability": {"state": "available"},
    }
    if author.get("name"):
        post["author"]["display_name"] = author["name"]
    if record.get("conversation_id"):
        post["conversation_id"] = record["conversation_id"]
    if record.get("reply_to"):
        post["parent_post_id"] = record["reply_to"]
    if record.get("created_at"):
        post["created_at"] = record["created_at"]
    if record.get("lang"):
        post["lang"] = record["lang"]
    post["text"] = {
        "canonical": text,
        "form": "authored",
        "supplied_by": supplied_by,
        "completeness": completeness,
    }
    entities = entities_from(text, facets or []) + mentions_from(text, record)
    if entities:
        post["text"]["entities"] = sorted(entities, key=lambda e: e["start_char"])
    media = []
    for item in record.get("media") or []:
        entry = {"type": item["type"], "url": item["url"]}
        for key in ("key", "width", "height", "duration_ms"):
            if item.get(key) is not None:
                entry[key] = item[key]
        if item.get("alt_text"):
            entry["alt_text"] = item["alt_text"]
        variants = [
            {
                k: v
                for k, v in (
                    ("url", var.get("url")),
                    ("content_type", var.get("content_type")),
                    ("bitrate", var.get("bitrate")),
                )
                if v is not None
            }
            for var in item.get("variants") or []
        ]
        if variants:
            entry["variants"] = variants
        media.append(entry)
    if media:
        post["media"] = media
    quoted = record.get("quoted") or {}
    if quoted.get("id") and (quoted.get("author") or {}).get("username"):
        post["quote"] = {
            "quoted_post_id": quoted["id"],
            "quoted_author_username": quoted["author"]["username"],
        }
    return post
