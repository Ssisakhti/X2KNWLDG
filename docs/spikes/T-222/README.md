# `T-222` — acquisition qualification spike

This directory is **evidence, not product**. Nothing here is imported by
`x2knwldg`, nothing writes into `output/`, and no provider is integrated. Its
only job is to record what each credential-free route into X actually returns
from the machine it is run on, so that `T-223` can freeze a capture contract
around observed data instead of a provider's documentation.

Read [`REPORT.md`](REPORT.md) for the capability table and the go/no-go.

## Layout

| File | What it is |
|---|---|
| [`REPORT.md`](REPORT.md) | The spike report: capability matrix, findings, decision |
| [`cases.json`](cases.json) | The matrix definition — refs, why each was chosen, what a route must observe to `PASS` |
| [`qualify.py`](qualify.py) | The harness. Stdlib only, imports nothing from the package |
| `results.json` | Generated. Every cell with its verdict, reason, latency, digests |
| `fixtures/` | Generated. Sanitized response bodies, one per cell |

## Reproducing it

The provider is a **separately installed, pinned** tool, never a build
dependency of this project (ADR 0007, and the licence boundary in `T-224`):

```bash
# tamnd/x-cli v0.5.0 — AGPL-3.0, Go, no API key, read-only
curl -sSLO https://github.com/tamnd/x-cli/releases/download/v0.5.0/x_0.5.0_darwin_arm64.tar.gz
curl -sSLO https://github.com/tamnd/x-cli/releases/download/v0.5.0/checksums.txt
shasum -a 256 -c checksums.txt --ignore-missing   # must say OK
tar xzf x_0.5.0_darwin_arm64.tar.gz               # yields ./x

python3 docs/spikes/T-222/qualify.py --xcli ./x --rate 1.2
```

Exit `0` means every cell was measured, `1` that a cell failed, `2` that the
credential scan rejected a fixture.

`--rate` matters. `x tweet` reads a surface with no observed budget, but the
archive read used for the thread measurement is `graphql.UserTweets` at
**500 per 15 minutes**, and the syndication profile surface is **30 per 15
minutes**. A run that trips either gets a rate limit, and the harness marks the
affected measurement `measured: false` rather than scoring it — a transport
failure is not evidence about a capability.

## What is deliberately not here

- **No credential of any kind.** The spike ran at Tier 0 (no token) and Tier 1
  (an anonymous guest token X mints on request). No X session was configured,
  no cookie jar, browser profile or account was read, and `x auth import` was
  never run. `results.json` records the tier every cell used.
- **No private material.** Every ref is a public post by an institutional
  account.
- **No raw HTML of the `x.com` surface.** It is ~327 KB per post, is
  presentation rather than contract, and its digest is enough for this task.

## Sanitization

`qualify.py` redacts before writing and then re-scans; a match that survives
fails the run with exit `2`. `results.json` records, per fixture, the raw
digest, the sanitized digest, and what sanitization removed.

The one thing actually found in the bodies was the syndication surface's
`token` query parameter. It is derived from the post id and `x surfaces` notes
it "is not validated", so it is not a credential — but it is request material,
so it is stripped, and x-cli recomputes it from the id when the fixture is
reproduced.

That pattern is worth keeping in mind for `T-223`: the first version of the
stripper matched `?token=` and `&token=` and reported a clean sweep across all
52 cells, while ten fixtures carried the token in x-cli's JSON, where the
ampersand arrives JSON-escaped as `\u0026`. The scan is only as good as the encodings it
knows about, which is why it now runs as a separate enforced pass rather than
trusting the redaction step's own report.
