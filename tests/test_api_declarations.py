"""`T-115` — from what is **served** to what the frontend compiles against.

Three guards already stand along the contract, and there was a gap between the
last two:

1. ``tools/generate_api_types.py`` renders ``schemas/api/v1/openapi.json`` into
   ``types.d.ts``, and ``tests/test_api_types.py`` fails if the committed file
   is stale.
2. ``web-typecheck`` proves the result is valid TypeScript (`tsc --strict`, R17).
3. ``test_api_hardening.test_the_served_surface_is_exactly_the_frozen_one``
   proves the app serves exactly the frozen **paths**.

What none of them can do is look at a response. `tsc` has no body at compile
time; the generator never runs the server; the paths check stops at the URL. So
the declarations the Library and the Reader are written against were guarded
against a *document*, and the document was guarded against the app's *routing
table* — and nothing joined the two ends. A route could serve a shape the
frontend has no declaration for and every one of the three would stay green.

This file closes that loop, in both directions:

* **Shape.** Every endpoint is called against a real project, over both
  repository implementations, and the body is checked against the ``response``
  type declared for that operation — parsed out of ``types.d.ts`` itself by
  :mod:`ts_declarations`, not out of the JSON Schema it was generated from.
  Checking against the schema again would only re-run
  ``api_harness.assert_contract``.
* **Calling convention.** The operations, paths, methods and parameters the app
  actually serves are compared with the ones ``Endpoints`` declares. A query
  parameter a route grew but the declarations do not have is unreachable from
  the frontend; one the declarations have but no route reads is a promise the
  server does not keep.

The checker is checked too. A validator that accepts everything reports
agreement it never established, so the mutation tests in section 4 feed it
bodies that are wrong in each of the ways a real body goes wrong and require it
to say so.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import api_harness as h
import pytest
import ts_declarations as ts

#: The declarations the frontend imports. Only the live half of this file needs
#: the framework; the parser and its mutation tests are stdlib-only and run on a
#: bare core install, for the reason `tests/test_api_types.py` is.
TYPES_PATH = h.API_DIR / "types.d.ts"

#: The ids the fixture project answers for, per path template. Real ones: a
#: request built from a placeholder would be testing the 404 path.
FIXTURE_IDS = {
    "{source_id}": "youtube:fixture-pass",
    "{entity_id}": "youtube:fixture-pass:KU-000001",
    "{artifact_id}": "youtube:fixture-pass:report",
}

#: Values for the required query parameters, by name. `search` is the only
#: operation with one.
REQUIRED_QUERY = {"q": "evidence"}

#: A header parameter has no slot in the declarations — the generated
#: `Endpoints` entries carry `path`, `method`, `params`, `query` and `response`
#: and nothing else. `Range` is the only one the contract defines, and
#: `tests/test_api_media.py` owns its behaviour. Named here so the omission is a
#: decision on the record rather than something this test quietly overlooks.
UNDECLARED_HEADERS = {"Range"}


@pytest.fixture(scope="module")
def declarations() -> ts.Declarations:
    return ts.parse(TYPES_PATH)


@pytest.fixture(scope="module")
def served() -> dict[str, Any]:
    """The document the **app** generates, which is what it says it serves."""
    from x2knwldg.repository import MemoryRepository
    from x2knwldg.server.app import create_app

    return create_app(repository=MemoryRepository.unavailable("absent")).openapi()


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return h.project(tmp_path_factory.mktemp("declarations"))


def request_for(declarations: ts.Declarations, spec: ts.TypeExpression) -> tuple[str, dict]:
    """A URL and query built from the declaration alone.

    Deliberately from the declaration and not from a hand-written table: the
    question this file asks is whether a client holding only ``types.d.ts`` can
    reach the endpoint, so the request has to come from there.
    """
    url = declarations.resolve(spec.member("path")).literal
    for placeholder, value in FIXTURE_IDS.items():
        url = url.replace(placeholder, value)
    query = {
        name: REQUIRED_QUERY[name]
        for name, optional, _ in declarations.resolve(spec.member("query")).members
        if not optional
    }
    return url, query


# --------------------------------------------------------------------------
# 1. The declarations are readable at all
# --------------------------------------------------------------------------


def test_every_declaration_parses(declarations: ts.Declarations) -> None:
    """The reader refuses what it does not understand, so parsing is a check.

    If the generator grows a construct this reader has no grammar for, `parse`
    raises and this fails — which is the intended failure. A checker that
    shrugged at an unfamiliar construct would go on reporting agreement about
    the parts it still understood.
    """
    assert declarations.types, "the declarations parsed to nothing"
    assert "Endpoints" in declarations.types


def test_every_named_type_resolves(declarations: ts.Declarations) -> None:
    """No declaration refers to a name the file does not define."""
    def walk(expression: ts.TypeExpression) -> None:
        declarations.resolve(expression)
        for option in expression.options:
            walk(option)
        for _, _, member in expression.members:
            walk(member)
        if expression.element is not None:
            walk(expression.element)

    for name, expression in declarations.types.items():
        try:
            walk(expression)
        except ts.UnsupportedDeclaration as exc:  # pragma: no cover - the message is the point
            pytest.fail(f"{name}: {exc}")


# --------------------------------------------------------------------------
# 2. The calling convention the app serves is the one declared
# --------------------------------------------------------------------------


@h.requires_fastapi
def test_the_declarations_cover_exactly_the_served_operations(
    declarations: ts.Declarations, served: dict[str, Any]
) -> None:
    """One declaration per served path and method — not one fewer, not one more.

    ``test_the_served_surface_is_exactly_the_frozen_one`` compares the app with
    the frozen document. This compares the app with the file the frontend
    imports, which is a different artifact and can go stale on its own.
    """
    served_pairs = {
        (path, method) for path, operations in served["paths"].items() for method in operations
    }
    declared_pairs = {
        (
            declarations.resolve(spec.member("path")).literal,
            declarations.resolve(spec.member("method")).literal,
        )
        for spec in declarations.endpoints.values()
    }
    assert declared_pairs == served_pairs, (
        f"undeclared: {sorted(served_pairs - declared_pairs)}; "
        f"unserved: {sorted(declared_pairs - served_pairs)}"
    )


@h.requires_fastapi
def test_every_parameter_the_app_reads_is_declared(
    declarations: ts.Declarations, served: dict[str, Any]
) -> None:
    """Path and query parameters, by name and by whether they are required.

    A parameter a route reads but the declarations lack is unreachable from a
    typed client; one the declarations promise but no route reads is a promise
    the server does not keep. Headers are excluded by
    :data:`UNDECLARED_HEADERS`, and the exclusion is asserted rather than
    assumed.
    """
    by_path = {
        declarations.resolve(spec.member("path")).literal: spec
        for spec in declarations.endpoints.values()
    }
    for path, operations in served["paths"].items():
        spec = by_path[path]
        for method, operation in operations.items():
            parameters = operation.get("parameters", [])
            headers = {p["name"] for p in parameters if p["in"] == "header"}
            assert headers <= UNDECLARED_HEADERS, f"{method.upper()} {path} grew a header"

            for slot, location in (("params", "path"), ("query", "query")):
                served_here = {
                    p["name"]: bool(p.get("required")) for p in parameters if p["in"] == location
                }
                declared_here = {
                    name: not optional
                    for name, optional, _ in declarations.resolve(spec.member(slot)).members
                }
                assert declared_here == served_here, (
                    f"{method.upper()} {path} {slot}: "
                    f"declared {declared_here}, served {served_here}"
                )


# --------------------------------------------------------------------------
# 3. The loop closed: a served body satisfies the declared response type
# --------------------------------------------------------------------------


def _operations(declarations: ts.Declarations) -> list[str]:
    return sorted(declarations.endpoints)


@h.requires_fastapi
@pytest.mark.parametrize("operation", _operations(ts.parse(TYPES_PATH)))
def test_the_served_body_satisfies_the_declared_response_type(
    declarations: ts.Declarations, root: Path, operation: str
) -> None:
    """The declaration the frontend compiles against, checked against real bytes.

    Over both implementations, because D-052: the oracle answered correctly
    while `SqliteRepository` `503`'d on every request, so a body checked only
    against `MemoryRepository` says nothing about the server that ships.
    """
    spec = declarations.endpoints[operation]
    response_type = spec.member("response")
    url, query = request_for(declarations, spec)

    for label, client in h.both_clients(root):
        response = client.get(url, params=query)
        assert response.status_code == 200, f"{label} {url}: {response.status_code} {response.text}"

        if declarations.resolve(response_type).name == "Blob":
            # Bytes, by declaration. A JSON body here would mean the frontend
            # is typed for a download and served a document.
            assert not response.headers["content-type"].startswith("application/json")
            assert response.content
            continue

        problems = ts.violations(response.json(), response_type, declarations)
        assert not problems, f"{label} {operation} violated its declaration:\n  " + "\n  ".join(
            problems
        )


@h.requires_fastapi
def test_a_refusal_satisfies_the_declared_error_response(
    declarations: ts.Declarations, root: Path
) -> None:
    """Every error shape a client can provoke, against ``ErrorResponse`` as declared.

    The envelope is what a frontend's error path is written against, and it is
    the one shape produced by handlers rather than by routes — so it is the one
    most likely to drift from the declarations without any route changing.
    """
    error_type = ts.TypeExpression("name", name="ErrorResponse")
    with h.client(h.memory_repository(root)) as client:
        refusals = [
            client.get("/api/sources/notasourceid"),  # 400 invalid_id
            client.get("/api/sources/youtube:no-such-run"),  # 404 not_found
            client.get("/api/sources", params={"status": "GREAT"}),  # 400 invalid_request
            client.get("/api/sources", params={"limit": "abc"}),  # 400, not a framework 422
            client.get("/api/graph/neighborhood/youtube:fixture-pass:KU-000001?depth=9"),
        ]
        for response in refusals:
            assert response.status_code >= 400, response.text
            problems = ts.violations(response.json(), error_type, declarations)
            assert not problems, f"{response.url} violated ErrorResponse:\n  " + "\n  ".join(
                problems
            )


# --------------------------------------------------------------------------
# 4. The checker itself — a green result must be able to be red
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def a_source() -> dict[str, Any]:
    """A minimal value that satisfies the declared ``Source``, built by hand."""
    return {
        "schema_version": "1.0",
        "id": "youtube:abc",
        "source_type": "youtube",
        "external_id": "abc",
        "canonical_dir": "output/abc",
        "status": {"validation": "PASS", "coverage": "PASS", "overall": "PASS"},
        "adapter": {"name": "youtube", "version": "1.0"},
    }


def check(declarations: ts.Declarations, value: Any, name: str = "Source") -> list[str]:
    return ts.violations(value, ts.TypeExpression("name", name=name), declarations)


def test_the_checker_accepts_a_valid_record(
    declarations: ts.Declarations, a_source: dict[str, Any]
) -> None:
    assert check(declarations, a_source) == []


def test_a_missing_required_member_is_caught(
    declarations: ts.Declarations, a_source: dict[str, Any]
) -> None:
    problems = check(declarations, {k: v for k, v in a_source.items() if k != "canonical_dir"})
    assert problems == ["$.canonical_dir: required, and missing"]


def test_an_undeclared_member_is_caught(
    declarations: ts.Declarations, a_source: dict[str, Any]
) -> None:
    """A field the frontend has no declaration for is a field nothing describes."""
    problems = check(declarations, {**a_source, "verdict": "PASS"})
    assert problems == ["$.verdict: not declared"]


def test_a_wrong_scalar_type_is_caught(
    declarations: ts.Declarations, a_source: dict[str, Any]
) -> None:
    assert check(declarations, {**a_source, "duration_sec": "90"}) != []
    assert check(declarations, {**a_source, "duration_sec": 90.0}) == []
    assert check(declarations, {**a_source, "duration_sec": None}) == []


def test_a_value_outside_a_literal_union_is_caught(
    declarations: ts.Declarations, a_source: dict[str, Any]
) -> None:
    """`RunStatus` is four literals, and `SUCCESS` is not one of them."""
    coerced = {**a_source, "status": {**a_source["status"], "overall": "SUCCESS"}}
    assert check(declarations, coerced) != []


def test_a_boolean_is_not_a_number(declarations: ts.Declarations) -> None:
    """`True` is an `int` in Python and is not a number in JSON."""
    assert ts.violations(True, ts.TypeExpression("name", name="Confidence"), declarations) != []


def test_an_optional_member_may_be_absent_but_not_wrong(
    declarations: ts.Declarations, a_source: dict[str, Any]
) -> None:
    assert "title" not in a_source
    assert check(declarations, a_source) == []
    assert check(declarations, {**a_source, "title": 7}) != []


def test_an_array_element_is_checked(
    declarations: ts.Declarations, a_source: dict[str, Any]
) -> None:
    assert check(declarations, {**a_source, "artifact_ids": ["youtube:abc:report"]}) == []
    assert check(declarations, {**a_source, "artifact_ids": [7]}) != []
    assert check(declarations, {**a_source, "artifact_ids": "youtube:abc:report"}) != []


def test_an_open_record_accepts_anything_but_must_still_be_an_object(
    declarations: ts.Declarations, a_source: dict[str, Any]
) -> None:
    """`adapter_metadata` is open by design — open is not the same as unchecked."""
    assert check(declarations, {**a_source, "adapter_metadata": {"anything": [1, 2]}}) == []
    assert check(declarations, {**a_source, "adapter_metadata": ["not", "an", "object"]}) != []


def test_a_response_envelope_missing_its_version_is_caught(declarations: ts.Declarations) -> None:
    """The envelope's constants are literal types, so an empty one is not a shape."""
    assert check(declarations, {"data": [], "page": {}}, "SourceListResponse") != []


# --------------------------------------------------------------------------
# 5. The parser refuses rather than guesses
# --------------------------------------------------------------------------


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "types.d.ts"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "declaration",
    [
        "export type Probe = string[];",  # a suffix array; the generator emits Array<T>
        "export type Probe = Partial<Source>;",  # a generic
        "export type Probe = string & number;",  # an intersection
        "export enum Probe { A }",  # not a type alias
        "export type Probe = { [key: string]: string };",  # an index signature
        "export type Probe = Record<number, string>;",  # a non-string key
        "export type Probe = ",  # truncated
    ],
)
def test_an_unhandled_construct_is_refused(tmp_path: Path, declaration: str) -> None:
    """The generator refuses what it cannot render; so must the reader of it."""
    with pytest.raises(ts.UnsupportedDeclaration):
        ts.parse(write(tmp_path, declaration))


def test_a_dangling_reference_is_refused(tmp_path: Path) -> None:
    declarations = ts.parse(write(tmp_path, "export type Probe = Missing;"))
    with pytest.raises(ts.UnsupportedDeclaration, match="declared nowhere"):
        ts.violations({}, declarations.types["Probe"], declarations)


def test_a_self_referential_alias_is_refused(tmp_path: Path) -> None:
    declarations = ts.parse(write(tmp_path, "export type Probe = Probe;"))
    with pytest.raises(ts.UnsupportedDeclaration, match="refers to itself"):
        ts.violations({}, declarations.types["Probe"], declarations)


def test_comments_do_not_reach_the_grammar(tmp_path: Path) -> None:
    """The generated file is mostly documentation; none of it is syntax."""
    source = """
    /**
     * A doc comment holding export type Trap = never; and a { brace.
     */
    // A line comment holding a ; and a }.
    export type Probe = { a: string; };
    """
    declarations = ts.parse(write(tmp_path, source))
    assert set(declarations.types) == {"Probe"}
    assert ts.violations({"a": "x"}, declarations.types["Probe"], declarations) == []


# --------------------------------------------------------------------------
# 5. D-084 — the frozen spec is *in* the package, or it is served to nobody
# --------------------------------------------------------------------------
#
# `_FROZEN_SPEC` was `Path(__file__).resolve().parents[3] / "schemas" / …`,
# documented as "relative to the installed package" and in fact relative to a
# repo checkout — and there was no `[tool.setuptools.package-data]` and no
# `MANIFEST.in`, so no wheel carried the file. `GET /api/openapi.json` was
# permanently `404 {"detail": "spec not packaged"}` in every installed package,
# and CI could not see it: the `ui` job installs with `-e`, and the
# non-editable job has no fastapi and never touches the route.


def test_the_packaged_spec_is_byte_identical_to_the_authored_one() -> None:
    """Two copies, one contract. `schemas/api/v1/` stays the authored home.

    Located by path rather than by importing ``server.app``, so this runs on a
    bare core install: whether the package *carries* the file is a question
    about the distribution, not about fastapi being present.
    """
    import x2knwldg

    packaged = Path(x2knwldg.__file__).resolve().parent / "server" / "openapi.json"
    authored = Path(__file__).resolve().parents[1] / "schemas" / "api" / "v1" / "openapi.json"
    assert packaged.is_file(), "the package does not carry the spec it serves"
    assert packaged.read_bytes() == authored.read_bytes(), (
        "src/x2knwldg/server/openapi.json is stale; copy "
        "schemas/api/v1/openapi.json over it and commit the result"
    )


@h.requires_fastapi
def test_the_spec_resolves_from_beside_the_module_that_serves_it() -> None:
    """Not up the tree: `parents[3]` only exists in a checkout."""
    import x2knwldg.server.app as app_module
    from x2knwldg.server.app import _FROZEN_SPEC

    assert _FROZEN_SPEC.parent == Path(app_module.__file__).resolve().parent
    assert _FROZEN_SPEC.is_file()


def test_the_wheel_carries_the_spec() -> None:
    """The only check that actually proves an *installed* package can serve it."""
    import subprocess
    import sys
    import tempfile
    import zipfile

    project = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as directory:
        built = subprocess.run(
            [sys.executable, "-m", "pip", "wheel", "--no-deps", "-q", "-w", directory, str(project)],
            capture_output=True,
            text=True,
        )
        if built.returncode != 0:
            pytest.skip(f"pip wheel unavailable here: {built.stderr.strip()[:200]}")
        wheels = list(Path(directory).glob("*.whl"))
        assert wheels, "pip wheel produced nothing"
        names = zipfile.ZipFile(wheels[0]).namelist()
    assert "x2knwldg/server/openapi.json" in names, (
        "the wheel does not carry the frozen spec, so /api/openapi.json is a 404 "
        f"in every installed package; wheel holds: {sorted(names)[:20]}"
    )


@h.requires_fastapi
def test_the_route_serves_the_spec_rather_than_refusing(tmp_path: Path) -> None:
    root = h.project(tmp_path)
    with h.client(h.memory_repository(root)) as client:
        response = client.get("/api/openapi.json")
        assert response.status_code == 200, response.json()
        body = response.json()
        assert body["openapi"].startswith("3.1")
        assert body["paths"], "the served spec declares no paths"
