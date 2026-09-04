# Third-party notices

This file records the provenance of third-party source material included in
X2KNWLDG. It supplements, and does not replace, the repository's `LICENSE`
file or license notices embedded in individual files.

## youtube-to-knowledge

- Upstream project: [velmighty/youtube-to-knowledge](https://github.com/velmighty/youtube-to-knowledge)
- Original copyright: Copyright (c) 2025 velmighty
- License: MIT License

X2KNWLDG was derived from `youtube-to-knowledge` and retains both modified and
unmodified portions of its source code. The original copyright notice and MIT
permission notice are preserved in [`LICENSE`](LICENSE), as required when
copying or distributing the software or substantial portions of it.

X2KNWLDG adds and changes functionality including canonical transcript and
post capture handling, evidence provenance, structured knowledge units,
relationship and coverage data, validation, multi-source indexing, an
Obsidian-compatible Markdown export, agent workflows, and a local Knowledge
Canvas. New contributions are distributed under the repository's MIT License
unless an individual file explicitly states otherwise.

References to the upstream project or its author are for attribution and
provenance only. They do not imply affiliation, sponsorship, or endorsement.

The files retained substantially from upstream are isolated under
`legacy/upstream/` and documented in `legacy/upstream/README.md`. They are not
part of the maintained ingestion path; in particular, the upstream Whisper and
WhisperX drivers are never installed or invoked by X2KNWLDG.

## X/Twitter acquisition provider (external, not distributed)

The optional X/Twitter acquisition path invokes a separately installed copy of
[`tamnd/x-cli`](https://github.com/tamnd/x-cli), version `0.5.0`, licensed under
AGPL-3.0-only. X2KNWLDG does not copy, vendor, link, install, or redistribute that
program. It executes the user's local binary as a separate process, after
verifying its version and SHA-256 pin, and consumes its output through the
provider boundary described in
[`docs/adr/0007-twitter-acquisition-boundary.md`](docs/adr/0007-twitter-acquisition-boundary.md).
Existing capture metadata uses the shorter `AGPL-3.0` label; the provider's own
`NOTICE` identifies the precise SPDX expression as `AGPL-3.0-only`.

Invoking the separate provider does not by itself replace the license declared for
this repository's code. Anyone installing, modifying, or redistributing the provider
must comply with its license independently. If the boundary changes—for example, if
provider code or binaries are copied or distributed with X2KNWLDG—the licensing
analysis and this notice must be revisited. This notice records the current operational
boundary; it does not replace the provider's license text or constitute legal advice.

## The frontend's application framework (`web/`, Track C)

The Library, the Reader and the Map are a React application routed by React
Router. These are runtime dependencies of the browser bundle, not of the Python
package: the core distribution still installs nothing (ADR 0001 invariant 5),
and a checkout that never runs `npm ci` never fetches them.

Recorded here as D-203: this file claims to record what reaches the bundle, and
every package below reached it while none was listed. All MIT, so there was no
licence exposure — but a notices file that omits most of what it ships is a
record nobody can rely on, and "it happens to be MIT" is a fact that has to be
checked rather than assumed. `tests/test_ui_scaffold.py` now walks
`package-lock.json` for the production closure and fails on the next package
that reaches the bundle without a row here.

Verified 2026-09-03:

| Package | Licence | Upstream |
|---|---|---|
| `react@19.2.8` | MIT | [facebook/react](https://github.com/facebook/react) |
| `react-dom@19.2.8` | MIT | [facebook/react](https://github.com/facebook/react) |
| `react-router@7.18.3` | MIT | [remix-run/react-router](https://github.com/remix-run/react-router) |
| `react-router-dom@7.18.3` | MIT | [remix-run/react-router](https://github.com/remix-run/react-router) |

Pulled in transitively by those packages and therefore also present in the
bundle:

| Package | Licence | Upstream |
|---|---|---|
| `scheduler@0.27.0` | MIT | [facebook/react](https://github.com/facebook/react) |
| `cookie@1.1.1` | MIT | [jshttp/cookie](https://github.com/jshttp/cookie) |
| `set-cookie-parser@2.7.2` | MIT | [nfriedly/set-cookie-parser](https://github.com/nfriedly/set-cookie-parser) |

These four are ranges rather than exact pins in `package.json`, unlike the
renderer's. That is deliberate and is the distinction D-117 draws: the
renderer is pinned because it is a **prerelease** whose behaviour the Map
depends on in detail, and a range there would silently change the drawing.
These are stable majors, and the versions above are the ones
`package-lock.json` resolves — which is what a reproducible `npm ci` installs
and therefore what this record is about.

## Knowledge Map graph rendering (`web/`, Phase 2)

The frontend's Knowledge Map renders through Sigma over Graphology. These are
runtime dependencies of the browser bundle, not of the Python package: the core
distribution still installs nothing (ADR 0001 invariant 5), and a checkout that
never runs `npm ci` never fetches them.

Every version below is an **exact pin** rather than a range, and the versions
are part of the record: a licence checked at one version does not speak for a
later one. [ADR 0005](docs/adr/0005-knowledge-map-client.md) explains why the
renderer is pinned to one prerelease rather than tracked (D-117), and
`tests/test_ui_scaffold.py` fails if a pin turns into a range or drifts from
this file.

Chosen and verified during `T-202` (2026-09-02):

| Package | Licence | Upstream |
|---|---|---|
| `sigma@4.0.0-beta.5` | MIT | [sigmajs.org](https://www.sigmajs.org) |
| `graphology@0.26.0` | MIT | [graphology/graphology](https://github.com/graphology/graphology) |
| `graphology-types@0.24.8` | MIT | [graphology/graphology](https://github.com/graphology/graphology) |
| `graphology-layout-forceatlas2@0.10.1` | MIT | [graphology/graphology](https://github.com/graphology/graphology) |
| `@types/events@3.0.3` | MIT | [DefinitelyTyped](https://github.com/DefinitelyTyped/DefinitelyTyped) |

Pulled in transitively by those packages and therefore also present in the
bundle:

| Package | Licence | Upstream |
|---|---|---|
| `graphology-utils@2.5.2` | MIT | [graphology/graphology](https://github.com/graphology/graphology) |
| `events@3.3.0` | MIT | [Gozala/events](https://github.com/Gozala/events) |

`@types/events` carries no code into the bundle — it exists because Sigma's
published declarations `import "events"`, which ships no types of its own, and
`web/tsconfig.json` deliberately keeps `skipLibCheck: false` (risk R17). Sigma
v3 depends on `events` as well, so this is not particular to the v4 line.

All of the above are MIT-licensed, as is X2KNWLDG. No package here is
copyleft-licensed and none requires attribution beyond the notice preserved in
its own distributed files.

## The Knowledge Map's browser gate (`web/browser/`, Phase 2)

`T-209` walks the Map in a real browser, because jsdom has no WebGL and no
layout and a running server knows nothing about what was drawn. The harness
that drives it is a **development dependency only**: it is not imported by any
module under `web/src`, `npm run build` never sees it, and nothing it installs
reaches the browser bundle or the Python distribution.

Verified during `T-209` (2026-09-03):

| Package | Licence | Upstream |
|---|---|---|
| `@playwright/test@1.62.1` | Apache-2.0 | [microsoft/playwright](https://github.com/microsoft/playwright) |
| `playwright@1.62.1` | Apache-2.0 | [microsoft/playwright](https://github.com/microsoft/playwright) |
| `playwright-core@1.62.1` | Apache-2.0 | [microsoft/playwright](https://github.com/microsoft/playwright) |

Apache-2.0 rather than MIT, which is why these are recorded in a section of
their own rather than added to the table above: it is permissive and not
copyleft, and its attribution terms apply to redistribution of *its* files,
which this project does not do. The browsers Playwright downloads are not
redistributed here either -- they are fetched into a per-machine cache by
`npx playwright install`, outside the repository -- and the gate's recorded
walk was performed through the Google Chrome already installed on the target
machine (`channel: "chrome"`), which carries its own licence.
