#!/usr/bin/env python3
"""Generate TypeScript declarations from the frozen v1 API contract (``T-005``).

The generated file is ``schemas/api/v1/types.d.ts`` and it is **committed**.
``tests/test_api_types.py`` regenerates it in memory and fails if the result
differs, which is the same drift guard the run fixtures use: the contract and
the types the frontend compiles against cannot diverge without a red test.

Why a script here rather than ``openapi-typescript``
----------------------------------------------------

``T-005`` ran before ``T-008``, when there was no ``web/``, no ``package.json``,
and no Node job in CI. Adding an npm toolchain to produce one declaration file
would put the contract behind a dependency the core package deliberately does
not have (ADR 0001 invariant 5), and would have handed ``T-008`` a scaffold it
did not choose. Declarations are the whole output, the input is six closed
schemas plus one OpenAPI document, and the drift guard is a string comparison —
so stdlib is enough.

``T-008`` has since brought Node into CI, and this stays stdlib-only anyway: the
``web-typecheck`` job *checks* the committed file with ``tsc --noEmit`` rather
than producing it, so regenerating still needs nothing but Python. If the
frontend later wants ``openapi-typescript`` as a cross-check it can be added
without changing the contract, which is the artefact that matters.

What it will not do
-------------------

It handles exactly the JSON Schema constructs the v1 model uses and raises
:class:`UnsupportedSchema` on anything else, rather than emitting ``unknown``
and calling it a type. A silently degraded declaration is worse than a failed
build: the frontend would compile against a type that had quietly stopped
describing the contract. This mirrors what ``adapters/base.py`` does with a
value it cannot honestly map.

Two things TypeScript cannot express are emitted as documentation instead of
being dropped:

* the conditional ``allOf`` constraints on ``EntityRef``, ``Artifact``, and
  ``IndexedRelation`` — "a derived unit must carry ``derived_from``" is a
  runtime invariant the adapter enforces, not a shape;
* the cross-field invariants of ``schemas/v1/README.md``.

``Locator`` is the one ``allOf`` that *is* a shape: its branches are a
discriminated union tagged by ``type``, and it is declared as one. That is
stated in :data:`DISCRIMINATED_UNIONS` rather than sniffed, so a schema that
grows a conditional branch cannot be silently reinterpreted as a union.

Usage::

    python tools/generate_api_types.py            # write the file
    python tools/generate_api_types.py --check     # exit 1 if it is stale
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
V1_DIR = PROJECT_ROOT / "schemas" / "v1"
API_DIR = PROJECT_ROOT / "schemas" / "api" / "v1"
OPENAPI_PATH = API_DIR / "openapi.json"
OUTPUT_PATH = API_DIR / "types.d.ts"

#: The record schemas, and the TypeScript name each becomes. Explicit rather
#: than derived from ``title``, so renaming a title cannot rename a type the
#: frontend imports.
RECORD_TYPE_NAMES: Mapping[str, str] = {
    "source.schema.json": "Source",
    "artifact.schema.json": "Artifact",
    "locator.schema.json": "Locator",
    "entity_ref.schema.json": "EntityRef",
    "indexed_relation.schema.json": "IndexedRelation",
}

#: Schemas whose ``allOf`` is a discriminated union rather than a set of
#: conditional constraints, and the property that tags it.
DISCRIMINATED_UNIONS: Mapping[str, str] = {"locator.schema.json": "type"}

#: Keywords that carry no information for a TypeScript declaration. Anything
#: outside this set and the set the renderer handles is a refusal.
IGNORED_KEYWORDS = frozenset(
    {
        "$schema",
        "$id",
        "$comment",
        "title",
        "description",
        "examples",
        "default",
        "deprecated",
        "format",
        "pattern",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minItems",
        "maxItems",
        "uniqueItems",
        "discriminator",
    }
)

PRIMITIVES = {
    "string": "string",
    "number": "number",
    "integer": "number",
    "boolean": "boolean",
    "null": "null",
}

WRAP = 92


class UnsupportedSchema(RuntimeError):
    """A construct the generator will not guess at.

    Raised in preference to emitting a declaration that has stopped describing
    the contract.
    """


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _pascal(name: str) -> str:
    """``sourceType`` and ``source_type`` both become ``SourceType``."""
    parts = [part for part in name.replace("-", "_").split("_") if part]
    return "".join(part[:1].upper() + part[1:] for part in parts)


# --------------------------------------------------------------------------
# The name table — every $ref target, resolved to a TypeScript name
# --------------------------------------------------------------------------


def build_name_table(common: Mapping[str, Any], openapi: Mapping[str, Any]) -> dict[str, str]:
    """Map every ``$ref`` string the contract uses onto a declared type name.

    Both the relative form used inside ``schemas/v1/`` and the ``../../v1/``
    form used from the API document resolve to the same name, so the two
    documents cannot end up describing two different types for one schema.
    """
    table: dict[str, str] = {}
    taken: dict[str, str] = {}

    def claim(name: str, owner: str) -> None:
        previous = taken.get(name)
        if previous is not None and previous != owner:
            raise UnsupportedSchema(
                f"{owner} and {previous} both want the TypeScript name {name!r}; "
                "one schema, one type"
            )
        taken[name] = owner

    for key in common["$defs"]:
        name = _pascal(key)
        claim(name, f"common.schema.json#/$defs/{key}")
        for prefix in ("", "../../v1/"):
            table[f"{prefix}common.schema.json#/$defs/{key}"] = name

    for filename, name in RECORD_TYPE_NAMES.items():
        claim(name, filename)
        for prefix in ("", "../../v1/"):
            table[f"{prefix}{filename}"] = name

    for key in openapi["components"]["schemas"]:
        claim(key, f"openapi.json#/components/schemas/{key}")
        table[f"#/components/schemas/{key}"] = key

    return table


# --------------------------------------------------------------------------
# Rendering a schema as a TypeScript type expression
# --------------------------------------------------------------------------


class Renderer:
    def __init__(self, names: Mapping[str, str]) -> None:
        self.names = names

    # -- entry point ----------------------------------------------------

    def expression(self, schema: Any, owner: str, indent: int = 0) -> str:
        if not isinstance(schema, Mapping):
            raise UnsupportedSchema(f"{owner}: expected a schema object, got {type(schema).__name__}")

        keywords = set(schema) - IGNORED_KEYWORDS
        handled = {"$ref", "const", "enum", "oneOf", "anyOf", "type", "properties",
                   "required", "additionalProperties", "items", "allOf", "$defs"}
        unknown = keywords - handled
        if unknown:
            raise UnsupportedSchema(
                f"{owner}: {sorted(unknown)} is not handled. Extend the generator "
                "deliberately rather than letting the declaration drift from the schema"
            )

        if "$ref" in schema:
            return self._ref(schema["$ref"], owner)
        if "const" in schema:
            return json.dumps(schema["const"])
        if "enum" in schema:
            return " | ".join(json.dumps(value) for value in schema["enum"])
        if "oneOf" in schema:
            return self._union(schema["oneOf"], owner, indent)
        if "anyOf" in schema:
            return self._union(schema["anyOf"], owner, indent)
        if "allOf" in schema and "type" not in schema:
            raise UnsupportedSchema(
                f"{owner}: a bare allOf is not a shape this generator can name. "
                "Declare it in DISCRIMINATED_UNIONS or render its branches explicitly"
            )
        if "type" in schema:
            return self._typed(schema, owner, indent)
        raise UnsupportedSchema(f"{owner}: no type, $ref, enum, const, or union to render")

    # -- pieces ---------------------------------------------------------

    def _ref(self, ref: str, owner: str) -> str:
        try:
            return self.names[ref]
        except KeyError:
            raise UnsupportedSchema(f"{owner}: $ref {ref!r} names nothing this contract declares") from None

    def _union(self, members: Any, owner: str, indent: int) -> str:
        if not isinstance(members, list) or not members:
            raise UnsupportedSchema(f"{owner}: a union needs a non-empty list of members")
        return " | ".join(self.expression(member, f"{owner}[{i}]", indent) for i, member in enumerate(members))

    def _typed(self, schema: Mapping[str, Any], owner: str, indent: int) -> str:
        declared = schema["type"]
        types = declared if isinstance(declared, list) else [declared]
        rendered: list[str] = []
        for name in types:
            if name == "object":
                rendered.append(self._object(schema, owner, indent))
            elif name == "array":
                items = schema.get("items")
                if items is None:
                    raise UnsupportedSchema(f"{owner}: an array without items has no element type")
                rendered.append(f"Array<{self.expression(items, f'{owner}[]', indent)}>")
            elif name in PRIMITIVES:
                rendered.append(PRIMITIVES[name])
            else:
                raise UnsupportedSchema(f"{owner}: unknown type {name!r}")
        return " | ".join(rendered)

    def _object(self, schema: Mapping[str, Any], owner: str, indent: int) -> str:
        properties = schema.get("properties")
        if not properties:
            # adapter_metadata and ErrorBody.detail: open by design, so that an
            # adapter is never forced to drop canonical metadata.
            return "Record<string, unknown>"
        required = set(schema.get("required", []))
        pad = "  " * (indent + 1)
        lines: list[str] = ["{"]
        for key, subschema in properties.items():
            lines.extend(_doc(subschema.get("description"), pad))
            optional = "" if key in required else "?"
            expression = self.expression(subschema, f"{owner}.{key}", indent + 1)
            lines.append(f"{pad}{_key(key)}{optional}: {expression};")
        if schema.get("additionalProperties") is not False:
            lines.append(f"{pad}[key: string]: unknown;")
        lines.append("  " * indent + "}")
        return "\n".join(lines)


RULE = "// " + "-" * 73


def _section(title: str) -> str:
    return f"{RULE}\n// {title}\n{RULE}"


def _key(name: str) -> str:
    if name.isidentifier():
        return name
    return json.dumps(name)


def _doc(description: Any, pad: str) -> list[str]:
    if not isinstance(description, str) or not description.strip():
        return []
    text = description.replace("*/", "* /")
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        lines.extend(textwrap.wrap(paragraph.strip(), width=WRAP) or [""])
    body = [f"{pad} * {line}".rstrip() for line in lines]
    return [f"{pad}/**", *body, f"{pad} */"]


# --------------------------------------------------------------------------
# Declarations
# --------------------------------------------------------------------------


def _declare(name: str, schema: Mapping[str, Any], renderer: Renderer, extra_docs: list[str] | None = None) -> str:
    description = schema.get("description") or schema.get("title")
    doc_source = description
    if extra_docs:
        joined = "\n".join(extra_docs)
        doc_source = f"{description}\n\n{joined}" if description else joined
    lines = _doc(doc_source, "")
    lines.append(f"export type {name} = {renderer.expression(schema, name)};")
    return "\n".join(lines)


def _constraint_docs(schema: Mapping[str, Any], owner: str) -> list[str]:
    """The conditional ``allOf`` branches, as prose TypeScript cannot enforce."""
    branches = schema.get("allOf")
    if not branches:
        return []
    notes = ["Runtime invariants, enforced by the adapter and by the schemas — not by these types:"]
    for branch in branches:
        text = branch.get("description") or branch.get("title")
        if not text:
            raise UnsupportedSchema(
                f"{owner}: an allOf branch with neither title nor description would be "
                "silently dropped from the declaration"
            )
        notes.append(f"- {text}")
    return notes


def _locator(schema: Mapping[str, Any], tag: str, renderer: Renderer) -> list[str]:
    """Declare the discriminated union, one interface per branch."""
    blocks: list[str] = []
    members: list[str] = []
    for branch in schema["allOf"]:
        then = branch.get("then")
        if not isinstance(then, Mapping):
            raise UnsupportedSchema("Locator: every allOf branch must carry a then-schema")
        const = then.get("properties", {}).get(tag, {}).get("const")
        if not isinstance(const, str):
            raise UnsupportedSchema(
                f"Locator: a branch whose {tag!r} is not a string const is not a union member"
            )
        name = f"Locator{_pascal(const)}"
        members.append(name)
        docs = [text for text in (branch.get("title"), branch.get("description")) if text]
        blocks.append(_declare(name, {**then, "description": "\n\n".join(docs)}, renderer))
    union_doc = schema.get("description")
    blocks.append(
        "\n".join([*_doc(union_doc, ""), f"export type Locator = {' | '.join(members)};"])
    )
    return blocks


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------


def _resolve_parameter(parameter: Mapping[str, Any], openapi: Mapping[str, Any]) -> Mapping[str, Any]:
    ref = parameter.get("$ref")
    if ref is None:
        return parameter
    prefix = "#/components/parameters/"
    if not ref.startswith(prefix):
        raise UnsupportedSchema(f"parameter $ref {ref!r} is not a components/parameters reference")
    return openapi["components"]["parameters"][ref[len(prefix) :]]


def _endpoints(openapi: Mapping[str, Any], renderer: Renderer) -> str:
    lines = [
        *_doc(
            "Every operation of the frozen contract, keyed by operationId: its path, its "
            "parameters, and the body a 2xx carries. A typed fetch wrapper built on this "
            "cannot call a path the contract does not define or read a field it does not "
            "return.\n\nHeader parameters are omitted — the only one is the Range header of "
            "getArtifactMedia, which belongs to the transport rather than to the payload.",
            "",
        ),
        "export interface Endpoints {",
    ]
    for path, operations in openapi["paths"].items():
        for method, operation in operations.items():
            operation_id = operation["operationId"]
            params: dict[str, Any] = {}
            query: dict[str, Any] = {}
            required_params: set[str] = set()
            required_query: set[str] = set()
            for raw in operation.get("parameters", []):
                parameter = _resolve_parameter(raw, openapi)
                location = parameter["in"]
                if location == "header":
                    continue
                bucket, required = (params, required_params) if location == "path" else (query, required_query)
                bucket[parameter["name"]] = parameter["schema"]
                if parameter.get("required"):
                    required.add(parameter["name"])
            lines.extend(_doc(operation.get("summary"), "  "))
            lines.append(f"  {operation_id}: {{")
            lines.append(f'    path: {json.dumps(path)};')
            lines.append(f'    method: {json.dumps(method)};')
            lines.append(f"    params: {_bucket(params, required_params, renderer, f'{operation_id}.params')};")
            lines.append(f"    query: {_bucket(query, required_query, renderer, f'{operation_id}.query')};")
            lines.append(f"    response: {_response(operation, renderer, operation_id)};")
            lines.append("  };")
    lines.append("}")
    lines.append("")
    lines.extend(_doc("Every operationId the contract defines.", ""))
    lines.append("export type OperationId = keyof Endpoints;")
    return "\n".join(lines)


def _bucket(properties: Mapping[str, Any], required: set[str], renderer: Renderer, owner: str) -> str:
    if not properties:
        return "Record<string, never>"
    return renderer.expression(
        {"type": "object", "properties": dict(properties), "required": sorted(required), "additionalProperties": False},
        owner,
        indent=2,
    )


def _response(operation: Mapping[str, Any], renderer: Renderer, owner: str) -> str:
    for status in ("200", "206"):
        response = operation.get("responses", {}).get(status)
        if response is None:
            continue
        content = response.get("content", {})
        if "application/json" in content:
            return renderer.expression(content["application/json"]["schema"], f"{owner}.response")
        if "*/*" in content:
            return "Blob"
    raise UnsupportedSchema(f"{owner}: no 2xx response with a body to type")


# --------------------------------------------------------------------------
# The document
# --------------------------------------------------------------------------


def generate() -> str:
    common = _load(V1_DIR / "common.schema.json")
    openapi = _load(OPENAPI_PATH)
    records = {name: _load(V1_DIR / name) for name in RECORD_TYPE_NAMES}
    renderer = Renderer(build_name_table(common, openapi))

    blocks: list[str] = [
        "/**\n"
        " * X2KNWLDG local API — v1 TypeScript declarations.\n"
        " *\n"
        " * GENERATED FILE — do not edit by hand.\n"
        " * Source:    schemas/api/v1/openapi.json and schemas/v1/*.schema.json\n"
        " * Regenerate: python tools/generate_api_types.py\n"
        " * Guarded by: tests/test_api_types.py, which fails if this file is stale.\n"
        " *\n"
        " * Three cross-field invariants are beyond both JSON Schema and TypeScript and are\n"
        " * enforced by src/x2knwldg/ids.py at the point records are produced:\n"
        " * a global_id equals source_type:external_id:local_id, a Source.id equals\n"
        " * source_type:external_id, and a time_range locator does not end before it starts.\n"
        " */",
        _section("Shared primitives — schemas/v1/common.schema.json"),
    ]

    for key, schema in common["$defs"].items():
        blocks.append(_declare(_pascal(key), schema, renderer))

    blocks.append(_section("Index records — the response bodies, as the adapters produce them"))

    for filename, name in RECORD_TYPE_NAMES.items():
        schema = records[filename]
        if filename in DISCRIMINATED_UNIONS:
            blocks.extend(_locator(schema, DISCRIMINATED_UNIONS[filename], renderer))
            continue
        blocks.append(_declare(name, schema, renderer, _constraint_docs(schema, name)))

    blocks.append(_section("API envelopes — schemas/api/v1/openapi.json"))

    for name, schema in openapi["components"]["schemas"].items():
        blocks.append(_declare(name, schema, renderer))

    blocks.append(_section("Operations"))
    blocks.append(_endpoints(openapi, renderer))

    return "\n\n".join(blocks).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit 1 if the committed declarations are stale.",
    )
    args = parser.parse_args(argv)

    generated = generate()
    if args.check:
        current = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        if current != generated:
            print(
                f"{OUTPUT_PATH.relative_to(PROJECT_ROOT)} is stale; "
                "run python tools/generate_api_types.py",
                file=sys.stderr,
            )
            return 1
        print(f"{OUTPUT_PATH.relative_to(PROJECT_ROOT)} is up to date")
        return 0

    OUTPUT_PATH.write_text(generated, encoding="utf-8")
    print(f"wrote {OUTPUT_PATH.relative_to(PROJECT_ROOT)} ({len(generated.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
