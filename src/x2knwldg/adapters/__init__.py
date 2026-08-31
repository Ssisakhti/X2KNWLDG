"""Source adapters — canonical run directories mapped onto the v1 index model.

``T-004``. The index (``T-101``–``T-104``), the API (``T-105``–``T-107``), and
the board files all address entities by the three-part global id these adapters
produce; the canonical files keep their own names and their own contract.

Typical use::

    from x2knwldg.adapters import adapt_project

    records = adapt_project(project_root)
    for model, rows in records.by_model().items():
        ...

Adding a source type means writing a :class:`SourceAdapter` subclass and adding
it to :data:`ADAPTERS`. Nothing else in the stack changes — that is what ADR
0001 item 7 promises, and the shape of this module is what has to keep it true.
"""

from __future__ import annotations

from pathlib import Path

from .base import (
    MEDIA_TYPES,
    RUN_STATUSES,
    SCHEMA_VERSION,
    UNKNOWN_STATUS,
    AdapterError,
    IndexRecords,
    SourceAdapter,
    check_records,
    declared_source_type,
    media_type_for,
    project_relative,
    read_optional_json,
    read_status,
)
from .youtube import LIBRARY_DIR_NAME, YouTubeAdapter, adapt_library

#: Every adapter, by the source type it maps. The key is the first part of
#: every id the adapter produces.
ADAPTERS: dict[str, type[SourceAdapter]] = {
    YouTubeAdapter.source_type: YouTubeAdapter,
}

__all__ = [
    "ADAPTERS",
    "MEDIA_TYPES",
    "RUN_STATUSES",
    "SCHEMA_VERSION",
    "UNKNOWN_STATUS",
    "AdapterError",
    "IndexRecords",
    "SourceAdapter",
    "YouTubeAdapter",
    "adapt_library",
    "adapt_project",
    "adapt_run",
    "check_records",
    "declared_source_type",
    "get_adapter",
    "media_type_for",
    "project_relative",
    "read_optional_json",
    "read_status",
]


def get_adapter(source_type: str, project_root: Path) -> SourceAdapter:
    """The adapter for *source_type*, or a refusal naming what is registered."""
    try:
        adapter = ADAPTERS[source_type]
    except KeyError as exc:
        known = ", ".join(sorted(ADAPTERS)) or "none"
        raise AdapterError(
            f"no adapter is registered for source type {source_type!r} (registered: {known})"
        ) from exc
    return adapter(project_root)


def adapt_run(
    run_dir: Path, project_root: Path, *, hash_artifacts: bool = False
) -> IndexRecords:
    """Map one run, choosing the adapter from what its ``metadata.json`` declares."""
    run_dir = run_dir.expanduser().resolve()
    metadata = read_optional_json(run_dir / "metadata.json")
    if not isinstance(metadata, dict):
        raise AdapterError(f"{run_dir} has no readable metadata.json; it is not a run")
    adapter = get_adapter(declared_source_type(metadata), project_root)
    return adapter.adapt_run(run_dir, hash_artifacts=hash_artifacts)


def adapt_project(
    project_root: Path, *, output_dir: str = "output", hash_artifacts: bool = False
) -> IndexRecords:
    """Map every ingested source under ``output/``, plus the shared library.

    The scan is what ``T-102`` will make incremental: sorted for determinism,
    skipping dotfiles and the ``library/`` directory, which is not an ingested
    source but the cross-source index over all of them.
    """
    project_root = project_root.expanduser().resolve()
    output_root = project_root / output_dir
    records = IndexRecords()
    for metadata_path in sorted(output_root.glob("*/metadata.json")):
        run_dir = metadata_path.parent
        if run_dir.name.startswith(".") or run_dir.name == LIBRARY_DIR_NAME:
            continue
        records = records + adapt_run(
            run_dir, project_root, hash_artifacts=hash_artifacts
        )
    records = records + adapt_library(output_root / LIBRARY_DIR_NAME, project_root)
    return records
