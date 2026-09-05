"""Shared scaffolding for the Track B route tests.

Four route modules were written concurrently. Without this file each of them
would have grown its own client fixture, its own project builder and its own
notion of "does this body match the contract" — and the fourth copy is where
the three of them start to disagree.

What a route test needs, and gets here:

* :func:`client` — a ``TestClient`` over an app serving a chosen repository.
* :func:`memory_project` / :func:`sqlite_project` — the committed run fixtures
  as a real project root, answered by either implementation.
* :func:`assert_contract` — the response body validated against the **frozen**
  component in ``schemas/api/v1/openapi.json``. A route test that only checks
  ``response.status_code == 200`` is not a contract test.

Every route must be checked against *both* implementations. ``T-104`` proved
they answer identically, so a route that behaves differently on one of them has
found a route bug, not an implementation difference.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
V1_DIR = PROJECT_ROOT / "schemas" / "v1"
API_DIR = PROJECT_ROOT / "schemas" / "api" / "v1"
OPENAPI_PATH = API_DIR / "openapi.json"
OPENAPI_ID = "https://x2knwldg.local/schemas/api/v1/openapi.json"
FIXTURE_RUNS = PROJECT_ROOT / "tests" / "fixtures" / "runs"
SAMPLE_DIR = PROJECT_ROOT / "output" / "pqlWNihgdjI"

SCHEMA_FILES = (
    "common.schema.json",
    "source.schema.json",
    "artifact.schema.json",
    "locator.schema.json",
    "entity_ref.schema.json",
    "indexed_relation.schema.json",
)

#: The pipeline's own contract directory (`T-251`). The source-graph components
#: reach into it by relative ``$ref`` — a brief *is* a
#: ``source_knowledge.json``, and a relation's basis pair *is* the one the
#: canonical record declares — so a registry without these resolves nothing for
#: `T-254`'s two responses and :func:`assert_contract` would fail on the ref
#: rather than on the body.
SYNTHESIS_DIR = PROJECT_ROOT / "schemas" / "synthesis" / "v1"
SYNTHESIS_FILES = (
    "primitives.schema.json",
    "source_knowledge.schema.json",
    "source_relation.schema.json",
    "source_relations.schema.json",
)

ALL_FIXTURES = ("pass-run", "partial-run", "fail-run")

#: The whole API layer is the `ui` extra. On a bare core install these tests do
#: not run at all, which is the point of `T-009`: the core package must stay
#: importable and testable without `fastapi`.
requires_fastapi = pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None,
    reason="the API layer is the `ui` extra; the core package stays zero-dependency",
)

requires_sample = pytest.mark.skipif(
    not (SAMPLE_DIR / "metadata.json").exists(),
    reason="output/ is gitignored; the real sample exists only where a video was ingested",
)


def _has_fts5() -> bool:
    from x2knwldg.index.schema import has_fts5

    return has_fts5(sqlite3.connect(":memory:"))


requires_fts5 = pytest.mark.skipif(
    not _has_fts5(),
    reason="the migrations declare FTS5 tables, so a build needs an FTS5-enabled SQLite",
)


# --------------------------------------------------------------------------
# A project to serve
# --------------------------------------------------------------------------


def project(root: Path, *names: str, library: bool = True) -> Path:
    """A writable project root holding **copies** of the named run fixtures.

    The committed fixtures are evidence (`output/<id>/raw/` is immutable), so
    they are copied and never edited in place.
    """
    from x2knwldg.library import rebuild_library

    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)
    for name in names or ALL_FIXTURES:
        shutil.copytree(FIXTURE_RUNS / name, output / name)
    if library:
        rebuild_library(output)
    return root


def memory_repository(root: Path) -> Any:
    """A **fresh** oracle. D-042: the search corpus is a per-instance cache."""
    from x2knwldg.repository import MemoryRepository

    return MemoryRepository.from_project(root)


def sqlite_repository(root: Path, *, build: bool = True) -> Any:
    """The SQLite index at *root*, built first unless *build* is false.

    ``build=False`` is how a test reaches the ``absent`` state deliberately —
    the state a UI must be able to tell apart from "indexed and empty".
    """
    from x2knwldg.index.repository import SqliteRepository
    from x2knwldg.index.scanner import build_index
    from x2knwldg.index.search import document_indexer, search_retrieval

    if build:
        build_index(root, index_documents=document_indexer(root))
    return SqliteRepository.open(root, search=search_retrieval)


# --------------------------------------------------------------------------
# A client over it
# --------------------------------------------------------------------------


@contextmanager
def client(repository: Any) -> Iterator[Any]:
    """A ``TestClient`` over an app serving *repository*.

    ``raise_server_exceptions=False`` so that the generic ``internal`` handler
    is exercised as a client would see it, rather than the exception being
    re-raised into the test.

    ``base_url`` is a loopback address rather than TestClient's default
    ``http://testserver``, because D-103 added a ``Host`` allowlist and the
    default allowlist is the loopback set. Pointing the client at a real
    loopback name keeps every test speaking to the app the way a browser on
    this machine does — and keeps ``testserver`` *out* of the production
    allowlist, which is the whole point of having one.
    """
    from fastapi.testclient import TestClient

    from x2knwldg.server.app import create_app

    app = create_app(repository=repository)
    with TestClient(
        app, base_url="http://127.0.0.1", raise_server_exceptions=False
    ) as test_client:
        try:
            yield test_client
        finally:
            close = getattr(repository, "close", None)
            if close is not None:
                close()


def both_clients(root: Path) -> Iterator[tuple[str, Any]]:
    """Yield ``(label, client)`` for each implementation in turn.

    A generator rather than a context manager, because it yields twice: each
    client is opened, handed over, and closed before the next one is built. The
    label is what a failure message needs in order to say *which* implementation
    diverged.

    Use it as ``for label, client in both_clients(root):``. `T-104` proved the
    two answer identically, so a route that behaves differently on one of them
    has found a route bug, not an implementation difference.
    """
    with client(memory_repository(root)) as memory:
        yield "memory", memory
    with client(sqlite_repository(root)) as sqlite:
        yield "sqlite", sqlite


# --------------------------------------------------------------------------
# The frozen contract as an assertion
# --------------------------------------------------------------------------


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _registry() -> Any:
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    resources = [
        (schema["$id"], Resource.from_contents(schema))
        for schema in (
            *(_load(V1_DIR / name) for name in SCHEMA_FILES),
            *(_load(SYNTHESIS_DIR / name) for name in SYNTHESIS_FILES),
        )
    ]
    resources.append(
        (OPENAPI_ID, Resource.from_contents(_load(OPENAPI_PATH), default_specification=DRAFT202012))
    )
    return Registry().with_resources(resources)


_REGISTRY: Any = None


def contract_errors(component: str, instance: Any) -> list[str]:
    """Validation messages for *instance* against a frozen component. Empty is a pass."""
    global _REGISTRY
    from jsonschema import Draft202012Validator

    if _REGISTRY is None:
        _REGISTRY = _registry()
    validator = Draft202012Validator(
        {"$ref": f"{OPENAPI_ID}#/components/schemas/{component}"}, registry=_REGISTRY
    )
    return [error.message for error in validator.iter_errors(instance)]


def assert_contract(component: str, instance: Any) -> None:
    """Fail with the validator's own messages when *instance* violates the contract."""
    errors = contract_errors(component, instance)
    assert not errors, f"{component} violated:\n  " + "\n  ".join(errors)


def assert_error(response: Any, status: int, code: str) -> dict[str, Any]:
    """A refusal: the frozen ``ErrorResponse``, the right code, and no host path.

    The host-path check is D-051 generalised. A message that names an absolute
    path discloses the user's filesystem layout to any HTTP client, and ADR 0003
    forbids it — so every error body every route produces is checked for one,
    not only the one that was caught leaking.
    """
    assert response.status_code == status, f"expected {status}, got {response.status_code}: {response.text}"
    body = response.json()
    assert_contract("ErrorResponse", body)
    assert body["error"]["code"] == code, f"expected code {code!r}, got {body['error']['code']!r}"
    blob = json.dumps(body)
    assert str(PROJECT_ROOT) not in blob, f"an error body named a host path: {blob}"
    assert "/Users/" not in blob and "/home/" not in blob, f"an error body named a host path: {blob}"
    return body
