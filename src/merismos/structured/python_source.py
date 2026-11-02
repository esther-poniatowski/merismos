"""
Segmenter of Python sources: the docstrings of the module, its classes and its functions, and
its comments.

A docstring region carries its decoded value, dedented when the syntax asks for it, with its
pieces, and two attributes: the kind of its owner and the qualified name of the owner, as
`__qualname__` writes it. A comment region carries the text after its marker.

Each literal is decoded from the source text between the start and the end of its token, never
from the token string, which the tokenizer may normalize: it rewrites a line ending made of a
carriage return alone.

Classes
-------
DedentMode
    Dedent applied to a docstring.
PythonSyntax
    Strings that a Python segmenter extracts, and the dedent of docstrings.
PythonSegmenter
    Segmenter of Python sources under one syntax.

Functions
---------
parse_python_syntax(name, fields) -> PythonSyntax
    Parse the body of a Python syntax file.
"""

import ast
from bisect import bisect_left
from dataclasses import dataclass
from enum import Enum
import inspect
import re
import tokenize

from ..errors import DecodingError, SourceSyntaxError, SyntaxFileError
from ..lines import split_lines
from ..model import AttributeValue, DecodedString, Piece, Region, Segmentation, Span
from ..syntax import Fields
from . import kinds
from .base import StructuredSegmenter
from .python_strings import cleandoc, decode_literal
from .traced import TracedText


class DedentMode(Enum):
    """Dedent applied to a docstring: as `inspect.cleandoc`, or none."""

    CLEANDOC = "cleandoc"
    NONE = "none"


OWNER_KINDS = {
    ast.Module: "module",
    ast.ClassDef: "class",
    ast.FunctionDef: "function",
    ast.AsyncFunctionDef: "function",
}
"""Kind of the owner of a docstring, by the node class holding it."""

FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)
"""Nodes whose nested definitions are qualified by `<locals>`, as `__qualname__` writes them."""

LOCALS_QUALIFIER = "<locals>"
"""Part of a qualified name standing for the scope of a function."""

MODULE_NAME = "the module"
"""Name given in messages to the owner of a module docstring, which has no qualified name."""

CLEANDOC_TAB_SIZE = 8
"""Tab size of `str.expandtabs`, which `inspect.cleandoc` applies."""


@dataclass(frozen=True)
class PythonSyntax:
    """
    Strings that a Python segmenter extracts, and the dedent of docstrings.

    Attributes
    ----------
    owners : frozenset[str]
        Kinds of owners whose docstrings are extracted, among module, class and function.
    dedent : DedentMode
        Dedent applied to a docstring.
    comments : bool
        Whether comments are extracted.
    comment_exclusions : tuple[re.Pattern[str], ...]
        Patterns of the comment texts left out, such as directives to a linter, each matched at
        the start of the text after the comment marker.
    """

    owners: frozenset[str]
    dedent: DedentMode
    comments: bool
    comment_exclusions: tuple[re.Pattern[str], ...]


def parse_python_syntax(name: str, fields: Fields) -> PythonSyntax:
    """Parse the body of a Python syntax file, rejecting unknown keys and values."""
    owners = frozenset(fields.strings("docstring_owners"))
    unknown = owners - set(OWNER_KINDS.values())
    if unknown:
        raise SyntaxFileError(
            f"{name}: docstring_owners: unknown owner kind {sorted(unknown)[0]!r}"
        )
    dedent = fields.string("dedent")
    try:
        mode = DedentMode(dedent)
    except ValueError as error:
        choices = ", ".join(member.value for member in DedentMode)
        raise SyntaxFileError(f"{name}: dedent: expected one of {choices}") from error
    syntax = PythonSyntax(
        owners=owners,
        dedent=mode,
        comments=fields.boolean("comments"),
        comment_exclusions=fields.patterns("comment_exclusions"),
    )
    fields.finish()
    return syntax


@dataclass(frozen=True)
class _Docstring:
    """Docstring found in the tree: its owner, its value, and its offsets in the source."""

    owner: str
    name: str
    value: str
    start: int
    end: int


class _Positions:
    """Conversion of the rows and columns of the tokenizer and the tree to offsets."""

    def __init__(self, source: str) -> None:
        split = split_lines(source)
        self.lines = [source[line.start : line.next] for line in split]
        self._starts = [line.start for line in split]

    def offset(self, row: int, column: int) -> int:
        """Convert a row, from 1, and a column in code points to an offset."""
        if row > len(self._starts):
            # The tokenizer places its end marker on a row after the last line.
            return (self._starts[-1] + len(self.lines[-1])) if self._starts else 0
        return self._starts[row - 1] + column

    def offset_from_bytes(self, row: int, byte_column: int) -> int:
        """Convert a row and a column of the syntax tree, counted in UTF-8 bytes, to an offset."""
        column = len(self.lines[row - 1].encode("utf-8")[:byte_column].decode("utf-8"))
        return self.offset(row, column)


class PythonSegmenter(StructuredSegmenter[PythonSyntax]):
    """
    Segmenter of Python sources under one syntax.

    Parameters
    ----------
    syntax : PythonSyntax
        Strings to extract.
    source_type : str
        Name of the source type reported in each segmentation.
    """

    kinds = frozenset(kinds.PYTHON_KINDS)
    """Kinds of the regions that the segmenter returns."""

    def segment(self, source: str) -> Segmentation:
        """
        Segment a Python source.

        Raises
        ------
        SourceSyntaxError
            If the source does not parse as Python.
        DecodingError
            If a docstring decodes to another value than the one read by Python.
        """
        positions = _Positions(source)
        # The tokenizer reads the lines cut at every line ending that the syntax tree admits,
        # so that the rows of both index the same list.
        lines = iter(positions.lines)
        try:
            tree = ast.parse(source)
            tokens = list(tokenize.generate_tokens(lambda: next(lines, "")))
        except (SyntaxError, tokenize.TokenError) as error:
            raise SourceSyntaxError(f"invalid Python: {error}") from error
        strings = [
            (positions.offset(*token.start), positions.offset(*token.end))
            for token in tokens
            if token.type == tokenize.STRING
        ]
        regions = [
            self._docstring(source, docstring, strings)
            for docstring in self._docstrings(tree, positions)
        ]
        if self._syntax.comments:
            for token in tokens:
                if token.type == tokenize.COMMENT:
                    region = self._comment(source, positions, token)
                    if region is not None:
                        regions.append(region)
        return self._segmentation(source, regions)

    def _docstrings(self, tree: ast.Module, positions: _Positions) -> list[_Docstring]:
        """List the docstrings of the selected owners, with their offsets."""
        found: list[_Docstring] = []

        def visit(node: ast.AST, qualifier: str) -> None:
            """Collect the docstring of a node, then visit its children under its qualified name."""
            owner = OWNER_KINDS.get(type(node))
            # Only classes and functions name a scope; other nodes may carry a `name` of their own.
            name = node.name if isinstance(node, (ast.ClassDef, *FUNCTION_NODES)) else ""
            qualified = ".".join(part for part in (qualifier, name) if part)
            docstring = _docstring_expression(node)
            if owner in self._syntax.owners and docstring is not None:
                expression, value = docstring
                assert expression.end_lineno is not None and expression.end_col_offset is not None
                found.append(
                    _Docstring(
                        owner,
                        qualified,
                        value,
                        positions.offset_from_bytes(expression.lineno, expression.col_offset),
                        positions.offset_from_bytes(
                            expression.end_lineno, expression.end_col_offset
                        ),
                    )
                )
            nested = (
                f"{qualified}.{LOCALS_QUALIFIER}" if isinstance(node, FUNCTION_NODES) else qualified
            )
            for child in ast.iter_child_nodes(node):
                visit(child, nested)

        visit(tree, "")
        return found

    def _docstring(
        self, source: str, docstring: _Docstring, strings: list[tuple[int, int]]
    ) -> Region:
        """Build the region of a docstring from the string tokens lying inside its expression."""
        index = bisect_left(strings, (docstring.start, -1))
        parts: list[tuple[int, int]] = []
        while index < len(strings) and strings[index][1] <= docstring.end:
            parts.append(strings[index])
            index += 1
        if not parts:
            raise DecodingError(
                f"no string token for the docstring of {docstring.name or MODULE_NAME}"
            )
        traced = TracedText()
        for start, end in parts:
            traced.extend(decode_literal(source[start:end], start))
        decoded = traced.decoded(source, expected=docstring.value)
        if self._syntax.dedent is DedentMode.CLEANDOC:
            decoded = cleandoc(traced, CLEANDOC_TAB_SIZE).decoded(
                source, expected=inspect.cleandoc(docstring.value)
            )
        attributes: dict[str, AttributeValue] = {"owner": docstring.owner, "name": docstring.name}
        return Region(
            kinds.PYTHON_DOCSTRING,
            Span(parts[0][0], parts[-1][1]),
            attributes=attributes,
            string=decoded,
        )

    def _comment(
        self, source: str, positions: _Positions, token: tokenize.TokenInfo
    ) -> Region | None:
        """Build the region of a comment, its value the text after the marker, unless excluded."""
        start, end = positions.offset(*token.start), positions.offset(*token.end)
        value = source[start + 1 : end]
        if any(pattern.match(value) for pattern in self._syntax.comment_exclusions):
            return None
        pieces = (Piece(0, start + 1, len(value)),) if value else ()
        return Region(kinds.PYTHON_COMMENT, Span(start, end), string=DecodedString(value, pieces))


def _docstring_expression(node: ast.AST) -> tuple[ast.Constant, str] | None:
    """Return the expression of the docstring opening the body of a node, and its value."""
    body = getattr(node, "body", None)
    if not isinstance(body, list) or not body:
        return None
    first = body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return first.value, first.value.value
    return None
