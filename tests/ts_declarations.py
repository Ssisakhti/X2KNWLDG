"""A reader for ``schemas/api/v1/types.d.ts`` — the declarations, as a checker.

`tools/generate_api_types.py` turns the frozen OpenAPI document into TypeScript.
`tests/test_api_types.py` guards the generator against that document, and
``test_api_hardening.test_the_served_surface_is_exactly_the_frozen_one`` compares
the paths the app serves against the document's. Both ends were guarded; the
span between them was not. Nothing read a **served response** and asked whether
the frontend's declarations describe it.

This module is that missing half: it parses the generated file into types and
answers "does this JSON value satisfy this declared type". `tsc --strict`
already proves the declarations are valid TypeScript (`web-typecheck`, R17);
what it cannot do is see a response body, because no response exists at compile
time.

Stdlib only, deliberately — the same reason `tests/test_api_types.py` is:
`tools/generate_api_types.py` has no dependency and neither may its guard.

The grammar is small because the generated file is regular. Anything outside it
is **refused** rather than guessed at, for the reason the generator refuses:
a checker that quietly accepts a construct it does not understand goes on
reporting agreement it never established.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

__all__ = [
    "TypeExpression",
    "Declarations",
    "UnsupportedDeclaration",
    "parse",
    "violations",
]


class UnsupportedDeclaration(Exception):
    """The declarations hold a construct this reader does not understand."""


#: Types with no declaration of their own. ``Blob`` is the media endpoint's
#: response and is bytes rather than JSON, so it is named here and checked by
#: the caller rather than against a decoded body.
BUILTIN = frozenset({"string", "number", "boolean", "null", "unknown", "never", "Blob"})

_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)
_TOKEN = re.compile(r'"[^"]*"|[A-Za-z_$][A-Za-z0-9_$]*|[{}<>;:?,|=]')


def _tokenize(text: str) -> list[str]:
    """Every token, refusing any character the grammar has no token for.

    Skipping an unrecognised character is how a reader silently accepts what it
    cannot read: ``string[]`` with ``[`` and ``]`` dropped is indistinguishable
    from ``string``, and an array would have been checked as a scalar.
    """
    tokens: list[str] = []
    at = 0
    for match in _TOKEN.finditer(text):
        gap = text[at : match.start()]
        if gap.strip():
            raise UnsupportedDeclaration(f"{gap.strip()!r} is not part of the grammar")
        tokens.append(match.group())
        at = match.end()
    if text[at:].strip():
        raise UnsupportedDeclaration(f"{text[at:].strip()!r} is not part of the grammar")
    return tokens


# --------------------------------------------------------------------------
# The type language
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TypeExpression:
    """One node of the small type language the generated file uses.

    ``form`` is what the node is; the other fields carry whatever that form
    needs. Frozen, so a parsed declaration cannot be edited by the code checking
    against it.
    """

    form: str  # name | literal | union | object | array | record
    name: str = ""
    literal: str = ""
    options: tuple["TypeExpression", ...] = ()
    members: tuple[tuple[str, bool, "TypeExpression"], ...] = ()  # (name, optional, type)
    element: "TypeExpression | None" = None

    def member(self, name: str) -> "TypeExpression":
        """The type of object member *name*."""
        for member_name, _, member_type in self.members:
            if member_name == name:
                return member_type
        raise KeyError(name)


@dataclass
class Declarations:
    """Every ``export type``/``export interface`` in the file, by name."""

    types: dict[str, TypeExpression] = field(default_factory=dict)

    def resolve(self, expression: TypeExpression) -> TypeExpression:
        """Follow named references until something structural is reached."""
        seen: set[str] = set()
        while expression.form == "name" and expression.name not in BUILTIN:
            if expression.name in seen:
                raise UnsupportedDeclaration(f"{expression.name} refers to itself")
            seen.add(expression.name)
            if expression.name not in self.types:
                raise UnsupportedDeclaration(f"{expression.name} is declared nowhere")
            expression = self.types[expression.name]
        return expression

    @property
    def endpoints(self) -> dict[str, TypeExpression]:
        """The ``Endpoints`` interface, one entry per ``operationId``."""
        if "Endpoints" not in self.types:
            raise UnsupportedDeclaration("the declarations carry no Endpoints interface")
        return {name: value for name, _, value in self.types["Endpoints"].members}


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


class _Parser:
    def __init__(self, tokens: Sequence[str]) -> None:
        self._tokens = tokens
        self._at = 0

    def peek(self) -> str:
        return self._tokens[self._at] if self._at < len(self._tokens) else ""

    def next(self) -> str:
        token = self.peek()
        if not token:
            raise UnsupportedDeclaration("the declarations end mid-expression")
        self._at += 1
        return token

    def expect(self, token: str) -> None:
        found = self.next()
        if found != token:
            raise UnsupportedDeclaration(f"expected {token!r}, found {found!r}")

    def done(self) -> bool:
        return self._at >= len(self._tokens)

    # -- the grammar ------------------------------------------------------

    def type(self) -> TypeExpression:
        options = [self.primary()]
        while self.peek() == "|":
            self.next()
            options.append(self.primary())
        if len(options) == 1:
            return options[0]
        return TypeExpression("union", options=tuple(options))

    def primary(self) -> TypeExpression:
        token = self.next()
        if token == "{":
            return self.object()
        if token.startswith('"'):
            return TypeExpression("literal", literal=token[1:-1])
        if token == "Array":
            self.expect("<")
            element = self.type()
            self.expect(">")
            return TypeExpression("array", element=element)
        if token == "Record":
            self.expect("<")
            key = self.type()
            self.expect(",")
            value = self.type()
            self.expect(">")
            if key.form != "name" or key.name != "string":
                raise UnsupportedDeclaration(f"a Record keyed by {key} is not handled")
            return TypeExpression("record", element=value)
        if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", token):
            if self.peek() == "<":
                raise UnsupportedDeclaration(f"the generic {token} is not handled")
            return TypeExpression("name", name=token)
        raise UnsupportedDeclaration(f"{token!r} does not start a type")

    def object(self) -> TypeExpression:
        """``{`` already consumed."""
        members: list[tuple[str, bool, TypeExpression]] = []
        while self.peek() != "}":
            name = self.next()
            if not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", name):
                raise UnsupportedDeclaration(f"{name!r} is not a property name")
            optional = self.peek() == "?"
            if optional:
                self.next()
            self.expect(":")
            members.append((name, optional, self.type()))
            self.expect(";")
        self.expect("}")
        return TypeExpression("object", members=tuple(members))


def parse(path: Path) -> Declarations:
    """Read *path* and return every declaration it makes.

    Refuses on anything the grammar does not cover, so a generator change that
    emits a new construct fails here loudly instead of being skipped silently.
    """
    text = _COMMENT.sub(" ", path.read_text(encoding="utf-8"))
    parser = _Parser(_tokenize(text))
    declarations = Declarations()

    while not parser.done():
        parser.expect("export")
        keyword = parser.next()
        name = parser.next()
        if keyword == "type":
            parser.expect("=")
            if parser.peek() == "keyof":
                # `export type OperationId = keyof Endpoints;` — a derived name,
                # carrying no shape of its own.
                parser.next()
                parser.next()
                parser.expect(";")
                continue
            declarations.types[name] = parser.type()
            parser.expect(";")
        elif keyword == "interface":
            parser.expect("{")
            declarations.types[name] = parser.object()
        else:
            raise UnsupportedDeclaration(f"export {keyword} is not handled")
    return declarations


# --------------------------------------------------------------------------
# Checking a value against a declaration
# --------------------------------------------------------------------------


def violations(
    value: Any,
    expression: TypeExpression,
    declarations: Declarations,
    where: str = "$",
) -> list[str]:
    """Every way *value* fails to satisfy *expression*. Empty is a pass.

    Objects are checked **exactly**: a required member must be present, an
    optional one must satisfy its type when present, and an undeclared key is a
    violation. That is stricter than TypeScript's structural assignability and
    deliberately so — the declarations are generated from schemas that say
    ``additionalProperties: false``, so a key the frontend has no declaration
    for is a field the contract does not describe.
    """
    resolved = declarations.resolve(expression)

    if resolved.form == "name":
        return _builtin(value, resolved.name, where)
    if resolved.form == "literal":
        return [] if value == resolved.literal else [f"{where}: expected {resolved.literal!r}"]
    if resolved.form == "union":
        for option in resolved.options:
            if not violations(value, option, declarations, where):
                return []
        return [f"{where}: {value!r} matches no branch of the union"]
    if resolved.form == "array":
        if not isinstance(value, list):
            return [f"{where}: expected an array, found {type(value).__name__}"]
        assert resolved.element is not None
        return [
            problem
            for index, item in enumerate(value)
            for problem in violations(item, resolved.element, declarations, f"{where}[{index}]")
        ]
    if resolved.form == "record":
        if not isinstance(value, dict):
            return [f"{where}: expected an object, found {type(value).__name__}"]
        assert resolved.element is not None
        return [
            problem
            for key, item in value.items()
            for problem in violations(item, resolved.element, declarations, f"{where}.{key}")
        ]
    if resolved.form == "object":
        return _object(value, resolved, declarations, where)
    raise UnsupportedDeclaration(f"cannot check against {resolved.form}")


def _builtin(value: Any, name: str, where: str) -> list[str]:
    if name == "unknown":
        return []
    if name == "never":
        return [f"{where}: never admits no value, found {value!r}"]
    if name == "null":
        return [] if value is None else [f"{where}: expected null"]
    if name == "string":
        return [] if isinstance(value, str) else [f"{where}: expected a string"]
    if name == "boolean":
        return [] if isinstance(value, bool) else [f"{where}: expected a boolean"]
    if name == "number":
        # `bool` is an `int` in Python and is not a number in JSON.
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        return [] if ok else [f"{where}: expected a number"]
    if name == "Blob":
        return [f"{where}: Blob is bytes, not a decoded body"]
    raise UnsupportedDeclaration(f"unknown builtin {name}")


def _object(
    value: Any, expression: TypeExpression, declarations: Declarations, where: str
) -> list[str]:
    if not isinstance(value, dict):
        return [f"{where}: expected an object, found {type(value).__name__}"]
    problems: list[str] = []
    declared = {name for name, _, _ in expression.members}
    for name, optional, member_type in expression.members:
        if name not in value:
            if not optional:
                problems.append(f"{where}.{name}: required, and missing")
            continue
        problems.extend(violations(value[name], member_type, declarations, f"{where}.{name}"))
    for key in value:
        if key not in declared:
            problems.append(f"{where}.{key}: not declared")
    return problems
