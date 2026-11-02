"""
Registry of source types: the segmenter of each type, and the syntax that it reads by default.

The registry is the extension point of Merismos. A consumer segmenting a source type that
Merismos does not ship registers a builder of its own, and a consumer segmenting a shipped type
under another grammar passes its own syntax file. The default syntax of each shipped type is
declared in the packaged file `syntaxes/defaults.yml`, not in code, and the registry checks that
this file and the shipped builders name the same types.

Classes
-------
Segmenter
    Protocol of an object segmenting the sources of one type.
PackagedSyntax
    Reference to a syntax file shipped with Merismos.
SourceType
    Name of a source type with the builder of its segmenter.
Registry
    Source types known to a consumer, with their default syntaxes.

Functions
---------
default_registry() -> Registry
    Registry of the source types shipped with Merismos.
"""

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Callable, Iterable, Mapping, Protocol

import yaml

from .errors import SyntaxFileError, UnknownSourceTypeError
from .markdown.segmenter import MarkdownSegmenter
from .markdown.syntax import parse_markdown_syntax
from .model import Segmentation
from .structured.commit_source import CommitSegmenter, parse_commit_syntax
from .structured.python_source import PythonSegmenter, parse_python_syntax
from .structured.yaml_source import YamlSegmenter, parse_yaml_syntax
from .syntax import (
    PACKAGED_SYNTAXES,
    SyntaxDocument,
    load_syntax_document,
    packaged_syntax_document,
)

DEFAULTS_FILE = "defaults.yml"
"""Packaged file naming the default syntax of each shipped source type."""


class Segmenter(Protocol):
    """Protocol of an object segmenting the sources of one type."""

    @property
    def kinds(self) -> frozenset[str]:
        """Kinds of the regions that the segmenter returns."""

    def segment(self, source: str) -> Segmentation:
        """Segment one source."""


SegmenterBuilder = Callable[[SyntaxDocument, str], Segmenter]
"""Builder of a segmenter from a syntax document and the name of its source type."""


@dataclass(frozen=True)
class PackagedSyntax:
    """
    Reference to a syntax file shipped with Merismos, by its file name without extension.

    Attributes
    ----------
    name : str
        Name of the file in the package folder `syntaxes`.
    """

    name: str


SyntaxReference = PackagedSyntax | Path
"""Reference to a syntax file: a packaged syntax, or a file of the consumer."""


@dataclass(frozen=True)
class SourceType:
    """
    Name of a source type with the builder of its segmenter.

    Attributes
    ----------
    name : str
        Name under which consumers request the type.
    build : SegmenterBuilder
        Builder of a segmenter from a syntax document of the type.
    """

    name: str
    build: SegmenterBuilder


class Registry:
    """
    Source types known to a consumer, with their default syntaxes.

    Parameters
    ----------
    source_types : Iterable[SourceType]
        Source types to register.
    defaults : Mapping[str, SyntaxReference]
        Syntax read by default for each source type.
    """

    def __init__(
        self, source_types: Iterable[SourceType], defaults: Mapping[str, SyntaxReference]
    ) -> None:
        self._types = {source_type.name: source_type for source_type in source_types}
        self._defaults = {name: _resolved(reference) for name, reference in defaults.items()}

    def register(
        self, source_type: SourceType, default_syntax: SyntaxReference | None = None
    ) -> None:
        """
        Register a source type, replacing a type of the same name.

        Parameters
        ----------
        source_type : SourceType
            Source type to register.
        default_syntax : SyntaxReference | None
            Syntax read when a consumer requests the type without a syntax of its own. A path
            resolves when it is registered, so a later change of directory leaves it valid.
        """
        self._types[source_type.name] = source_type
        if default_syntax is not None:
            self._defaults[source_type.name] = _resolved(default_syntax)

    def names(self) -> tuple[str, ...]:
        """Return the names of the registered source types, sorted."""
        return tuple(sorted(self._types))

    def segmenter(self, source_type: str, syntax: Path | None = None) -> Segmenter:
        """
        Build the segmenter of a source type.

        Parameters
        ----------
        source_type : str
            Name of the source type.
        syntax : Path | None
            Syntax file to read, or None for the default syntax of the type.

        Raises
        ------
        UnknownSourceTypeError
            If no source type of that name is registered.
        SyntaxFileError
            If the syntax is invalid, or declares another source type.
        """
        try:
            builder = self._types[source_type].build
        except KeyError as error:
            known = ", ".join(self.names())
            raise UnknownSourceTypeError(
                f"unknown source type {source_type!r}; known: {known}"
            ) from error
        document = self._document(source_type, syntax)
        if document.source_type != source_type:
            raise SyntaxFileError(
                f"syntax {document.name!r} describes source type "
                f"{document.source_type!r}, not {source_type!r}"
            )
        return builder(document, source_type)

    def _document(self, source_type: str, syntax: Path | None) -> SyntaxDocument:
        """Read the syntax passed by the consumer, or the default syntax of the type."""
        reference = syntax if syntax is not None else self._defaults.get(source_type)
        if reference is None:
            raise SyntaxFileError(f"source type {source_type!r} has no default syntax")
        if isinstance(reference, PackagedSyntax):
            return packaged_syntax_document(reference.name)
        return load_syntax_document(reference)


def _resolved(reference: SyntaxReference) -> SyntaxReference:
    """Resolve a path reference, leaving a packaged reference unchanged."""
    return reference.resolve() if isinstance(reference, Path) else reference


def _build_markdown(document: SyntaxDocument, source_type: str) -> Segmenter:
    """Build the Markdown segmenter of a syntax document."""
    return MarkdownSegmenter(parse_markdown_syntax(document.name, document.body), source_type)


def _build_yaml(document: SyntaxDocument, source_type: str) -> Segmenter:
    """Build the YAML segmenter of a syntax document."""
    return YamlSegmenter(parse_yaml_syntax(document.name, document.body), source_type)


def _build_python(document: SyntaxDocument, source_type: str) -> Segmenter:
    """Build the Python segmenter of a syntax document."""
    return PythonSegmenter(parse_python_syntax(document.name, document.body), source_type)


def _build_commit(document: SyntaxDocument, source_type: str) -> Segmenter:
    """Build the commit segmenter of a syntax document."""
    return CommitSegmenter(parse_commit_syntax(document.name, document.body), source_type)


SHIPPED_BUILDERS: dict[str, SegmenterBuilder] = {
    "markdown": _build_markdown,
    "yaml": _build_yaml,
    "python": _build_python,
    "commit": _build_commit,
}
"""Builder of each shipped source type; the packaged defaults file names its syntax."""


def _packaged_defaults() -> dict[str, SyntaxReference]:
    """Read the default syntax of each shipped source type from the packaged defaults file."""
    resource = resources.files(__package__).joinpath(PACKAGED_SYNTAXES, DEFAULTS_FILE)
    data = yaml.safe_load(resource.read_text(encoding="utf-8"))
    defaults = data.get("defaults") if isinstance(data, Mapping) else None
    if not isinstance(defaults, Mapping) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in defaults.items()
    ):
        raise SyntaxFileError(
            f"{PACKAGED_SYNTAXES}/{DEFAULTS_FILE}: expected a mapping under defaults"
        )
    return {key: PackagedSyntax(value) for key, value in defaults.items()}


def default_registry() -> Registry:
    """
    Return a new registry of the source types shipped with Merismos.

    Raises
    ------
    SyntaxFileError
        If the packaged defaults file and the shipped builders name different types, which is a
        defect of the package.
    """
    defaults = _packaged_defaults()
    if set(defaults) != set(SHIPPED_BUILDERS):
        mismatch = ", ".join(sorted(set(defaults) ^ set(SHIPPED_BUILDERS)))
        raise SyntaxFileError(
            f"{PACKAGED_SYNTAXES}/{DEFAULTS_FILE} and the shipped types differ on: {mismatch}"
        )
    return Registry((SourceType(name, build) for name, build in SHIPPED_BUILDERS.items()), defaults)
