"""Twitter/X acquisition (Phase 2.2).

The provider seam ``T-224`` owns: a pinned, digest-verified local binary
(:mod:`.provider`), the bytes it returned preserved as immutable evidence
(:mod:`.evidence`), one record normalized away from the provider's shape
(:mod:`.normalize`), and the capture those three produce (:mod:`.acquire`).

Nothing here is imported by :mod:`x2knwldg.cli` at module scope, and nothing
here needs a third-party package: the acquisition path is ``subprocess`` and the
standard library, so ADR 0001 invariant 5 — a bare core install imports and runs
— holds with the seam present exactly as it did without it.

The opt-in network fallback and its corroboration (``T-225``) and passive
browser capture (``T-226``) are separate providers over the same contract. They
are not here, and this package does not reach for them: a capture states the one
route it read.
"""

from __future__ import annotations

__all__ = ["acquire", "evidence", "normalize", "provider"]
