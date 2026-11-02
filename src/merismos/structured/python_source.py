"""
Segmenter of Python sources: the docstrings of the module, its classes and its functions, and
its comments.

A docstring region carries its decoded value, dedented when the syntax asks for it, with its
pieces, and two attributes: the kind of its owner and the qualified name of the owner. A comment
region carries the text after its marker.

Classes
-------
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
from dataclasses import dataclass
import inspect
import io
import tokenize

from ..errors import DecodingError, SourceSyntaxError, SyntaxFileError
from ..model import AttributeValue, DecodedString, Piece, Region, Segmentation, Span
from ..syntax import Fields
from . import kinds
from .base import StructuredSegmenter
from .python_strings import cleandoc, decode_literal
from .traced import TracedText

DEDENT_MODES = ("cleandoc", "none")
"""Dedents of a docstring: as `inspect.cleandoc`, or none."""

OWNER_KINDS = {
    ast.Module: "module",
    ast.ClassDef: "class",
    ast.FunctionDef: "function",
    ast.AsyncFunctionDef: "function",
}
"""Kind of the owner of a docstring, by the node class holding it."""

SCOPE_NODES = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
"""Nodes whose name qualifies the docstrings nested in them."""

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
    dedent : str
        Dedent applied to a docstring: `cleandoc` or `none`.
    comments : bool
        Whether comments are extracted.
    """

    owners: frozenset[str]
    dedent: str
    comments: bool


def parse_python_syntax(name: str, fields: Fields) -> PythonSyntax:
    """Parse the body of a Python syntax file, rejecting unknown keys and values."""
    owners = frozenset(fields.strings("docstring_owners"))
    unknown = owners - set(OWNER_KINDS.values())
    if unknown:
        raise SyntaxFileError(
            f"{name}: docstring_owners: unknown owner kind {sorted(unknown)[0]!r}"
        )
    dedent = fields.string("dedent")
    if dedent not in DEDENT_MODES:
        choices = ", ".join(DEDENT_MODES)
        raise SyntaxFileError(f"{name}: dedent: expected one of {choices}")
    syntax = PythonSyntax(owners=owners, dedent=dedent, comments=fields.boolean("comments"))
    fields.finish()
    return syntax


@dataclass(frozen=True)
class _Docstring:
    """Docstring found in the tree: its owner, its value, and its lines and columns."""

    owner: str
    name: str
    value: str
    start: tuple[int, int]
    end: tuple[int, int]


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
        try:
            tree = ast.parse(source)
            tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        except (SyntaxError, tokenize.TokenError) as error:
            raise SourceSyntaxError(f"invalid Python: {error}") from error
        # The lines are cut as the tokenizer reads them, so that its rows index this list.
        lines = io.StringIO(source).readlines()
        line_starts = [0]
        for line in lines:
            line_starts.append(line_starts[-1] + len(line))
        regions = [
            self._docstring(source, docstring, tokens, line_starts)
            for docstring in self._docstrings(tree, lines)
        ]
        if self._syntax.comments:
            regions.extend(
                _comment(token, line_starts) for token in tokens if token.type == tokenize.COMMENT
            )
        return self._segmentation(source, regions)

    def _docstrings(self, tree: ast.Module, lines: list[str]) -> list[_Docstring]:
        """List the docstrings of the selected owners, with their positions in code points."""
        found: list[_Docstring] = []

        def visit(node: ast.AST, qualifier: str) -> None:
            owner = OWNER_KINDS.get(type(node))
            body = getattr(node, "body", None)
            # Only classes and functions name a scope; other nodes may carry a `name` of their own.
            name = node.name if isinstance(node, SCOPE_NODES) else ""
            qualified = ".".join(part for part in (qualifier, name) if part)
            if owner in self._syntax.owners and isinstance(body, list) and body:
                first = body[0]
                if (
                    isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)
                ):
                    expression = first.value
                    value: str = first.value.value
                    assert (
                        expression.end_lineno is not None and expression.end_col_offset is not None
                    )
                    found.append(
                        _Docstring(
                            owner,
                            qualified,
                            value,
                            (
                                expression.lineno,
                                _column(lines, expression.lineno, expression.col_offset),
                            ),
                            (
                                expression.end_lineno,
                                _column(lines, expression.end_lineno, expression.end_col_offset),
                            ),
                        )
                    )
            for child in ast.iter_child_nodes(node):
                visit(child, qualified)

        visit(tree, "")
        return found

    def _docstring(
        self,
        source: str,
        docstring: _Docstring,
        tokens: list[tokenize.TokenInfo],
        line_starts: list[int],
    ) -> Region:
        """Build the region of a docstring from the string tokens of its expression."""
        traced = TracedText()
        parts = [
            token
            for token in tokens
            if token.type == tokenize.STRING
            and docstring.start <= token.start
            and token.end <= docstring.end
        ]
        if not parts:
            raise DecodingError(
                f"no string token for the docstring of {docstring.name or MODULE_NAME}"
            )
        for token in parts:
            traced.extend(decode_literal(token.string, _offset(line_starts, token.start)))
        decoded = traced.decoded(source, expected=docstring.value)
        if self._syntax.dedent == "cleandoc":
            decoded = cleandoc(traced, CLEANDOC_TAB_SIZE).decoded(
                source, expected=inspect.cleandoc(docstring.value)
            )
        attributes: dict[str, AttributeValue] = {"owner": docstring.owner, "name": docstring.name}
        span = Span(_offset(line_starts, parts[0].start), _offset(line_starts, parts[-1].end))
        return Region(kinds.PYTHON_DOCSTRING, span, attributes=attributes, string=decoded)


def _offset(line_starts: list[int], position: tuple[int, int]) -> int:
    """Convert a line, from 1, and a column in code points to an offset."""
    return line_starts[position[0] - 1] + position[1]


def _column(lines: list[str], line: int, byte_column: int) -> int:
    """Convert a column of the syntax tree, counted in UTF-8 bytes, to code points."""
    return len(lines[line - 1].encode("utf-8")[:byte_column].decode("utf-8"))


def _comment(token: tokenize.TokenInfo, line_starts: list[int]) -> Region:
    """Build the region of a comment, whose value is its text after the marker."""
    start = _offset(line_starts, token.start)
    value = token.string[1:]
    pieces = (Piece(0, start + 1, len(value)),) if value else ()
    return Region(
        kinds.PYTHON_COMMENT,
        Span(start, start + len(token.string)),
        string=DecodedString(value, pieces),
    )
