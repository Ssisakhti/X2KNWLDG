# Twitter capture fixtures (T-223)

Built offline and deterministically by
[`build_captures.py`](build_captures.py) from raw evidence committed under
[`raw/`](raw/) and in `docs/spikes/T-222/fixtures/`. Re-running the builder must
leave `git status` clean — `tests/test_twitter_capture.py` asserts it, as
`tests/fixtures/runs/build_fixtures.py` does for the run fixtures (D-157).

```bash
.venv/bin/python tests/fixtures/captures/build_captures.py
git status --porcelain -- tests/fixtures/captures/    # expect: empty
```

| Fixture | Coverage | What it exists to cover |
|---|---|---|
| `pass-single-post-en.json` | `PASS` | The simplest real case, corroborated on two routes |
| `pass-single-post-fa.json` | `PASS` | Persian prose: ZWNJ and Persian digits, identical on both routes |
| `pass-single-post-fa-video.json` | `PASS` | Persian prose ending in an **LTR `t.co` run**: the only bidi span, and the only media with no `alt_text` |
| `pass-quote-post.json` | `PASS` | A quoted post as a separate cited source, plus mention spans |
| `pass-media-alt-text.json` | `PASS` | Author-written `alt_text`, and two URL entities with expansions |
| `pass-thread-terminal-anchor.json` | `PASS` | A real 10-post self-thread, root-first, walked from its terminal anchor |
| `partial-thread-root-anchor.json` | `PARTIAL` | Anchored at a root: descendants unenumerable, and named as omitted |
| `partial-tier0-truncated-text.json` | `PARTIAL` | Tier 0's silent truncation — 280 of 2967 characters |
| `fail-unavailable-post.json` | `FAIL` | A well-formed reference resolving to nothing on all three routes |

`pass-single-post-fa-video` was added for `T-227`. Its sibling
`pass-single-post-fa` is 418 characters of unbroken RTL prose carrying no entity
at all, so nothing in it exercises an offset; this one ends in a bare `t.co`
link at `[262, 285]`, an LTR run inside RTL text, which is where a bidi-naive
reading of a span goes wrong and nowhere else. The URL span comes from the
corroborating route, not the local one, which is D-218 stated as a fixture.

The three non-`PASS` fixtures are the point. `output/` is gitignored, so without
committed fixtures these tests would skip and the suite would be green having
proved nothing — and a fixture set of nothing but `PASS` documents would leave
the honest-degradation paths untested, which is the gap `T-006` had to fix for
the run fixtures.

## `raw/`

Ten preserved responses for the self-thread, one per post, recorded at Tier 1
with `--no-cache` and sanitized before commit. `MANIFEST.json` carries each
post's id, path and both digests. Nothing here contains a cookie, token, account
identifier or private post.
