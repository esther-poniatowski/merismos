"""
Syntax files: the declarative description of the grammar under which a source type is segmented.

A syntax file is a YAML document holding three header keys and the body of its source type:

- `syntax_version`, the version of the layout of syntax files read by this release;
- `source_type`, the name of the source type whose segmenter reads the body;
- `name`, the name of the syntax, such as `obsidian`.

Every other key belongs to the body, which the source type parses into its own typed syntax.
Merismos ships one syntax per source type in the package folder `syntaxes`, and a consumer may
pass a syntax file of its own instead.

Classes
-------
SyntaxDocument
    Header and body of one syntax file.
Fields
    Strict reader of a mapping of a syntax file, reporting each error with its key path.

Functions
---------
read_syntax_document(text, origin) -> SyntaxDocument
    Parse the text of a syntax file.
load_syntax_document(path) -> SyntaxDocument
    Read and parse a syntax file.
packaged_syntax_document(name) -> SyntaxDocument
    Read a syntax file shipped with Merismos.
"""

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
import re
from typing import Mapping, Sequence

import yaml

from .errors import SyntaxFileError

SYNTAX_VERSION = 1
"""Version of the layout of syntax files read by this release."""

HEADER_KEYS = frozenset({"syntax_version", "source_type", "name"})
"""Keys of a syntax file read by Merismos itself, before the body reaches its source type."""

PACKAGED_SYNTAXES = "syntaxes"
"""Package folder holding the syntax files shipped with Merismos."""


class Fields:
    """
    Strict reader of a mapping of a syntax file, reporting each error with its key path.

    A reader records the keys that it reads, and `finish` rejects every other key, so that a
    misspelled key fails instead of being ignored.

    Parameters
    ----------
    data : Mapping[str, object]
        Mapping to read.
    path : str
        Key path of the mapping in its file, used in error messages.
    origin : str
        Name of the file, used in error messages.

    Examples
    --------
    >>> fields = Fields({"fence": "---"}, "frontmatter", "example.yml")
    >>> fields.optional_string("fence")
    '---'
    >>> fields.finish()
    """

    def __init__(self, data: Mapping[str, object], path: str, origin: str) -> None:
        self._data = data
        self._path = path
        self._origin = origin
        self._read: set[str] = set()

    def _error(self, key: str, message: str) -> SyntaxFileError:
        """Build the error of a key, prefixed with the file and the key path."""
        location = f"{self._path}.{key}" if self._path else key
        return SyntaxFileError(f"{self._origin}: {location}: {message}")

    def _get(self, key: str) -> object:
        """Return the value of a key, recording that the key was read."""
        self._read.add(key)
        return self._data.get(key)

    def string(self, key: str) -> str:
        """Read a required non-empty string."""
        value = self._get(key)
        if not isinstance(value, str) or not value:
            raise self._error(key, "expected a non-empty string")
        return value

    def optional_string(self, key: str) -> str | None:
        """Read a non-empty string, or None when the key is absent or null."""
        if self._get(key) is None:
            return None
        return self.string(key)

    def boolean(self, key: str) -> bool:
        """Read a required boolean."""
        value = self._get(key)
        if not isinstance(value, bool):
            raise self._error(key, "expected true or false")
        return value

    def integer(self, key: str, minimum: int = 0) -> int:
        """Read a required integer, at least `minimum`."""
        value = self._get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise self._error(key, f"expected an integer of at least {minimum}")
        return value

    def strings(self, key: str) -> tuple[str, ...]:
        """Read a required list of non-empty strings, possibly empty."""
        value = self._get(key)
        if not isinstance(value, Sequence) or isinstance(value, str):
            raise self._error(key, "expected a list of strings")
        items: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item:
                raise self._error(key, "expected a list of non-empty strings")
            items.append(item)
        return tuple(items)

    def characters(self, key: str) -> tuple[str, ...]:
        """Read a required list of single characters."""
        items = self.strings(key)
        if any(len(item) != 1 for item in items):
            raise self._error(key, "expected a list of single characters")
        return items

    def character(self, key: str) -> str | None:
        """Read a single character, or None when the key is absent or null."""
        value = self.optional_string(key)
        if value is not None and len(value) != 1:
            raise self._error(key, "expected a single character")
        return value

    def pattern(self, key: str) -> re.Pattern[str] | None:
        """Read a regular expression, or None when the key is absent or null."""
        text = self.optional_string(key)
        if text is None:
            return None
        try:
            return re.compile(text)
        except re.error as error:
            raise self._error(key, f"invalid regular expression: {error}") from error

    def patterns(self, key: str) -> tuple[re.Pattern[str], ...]:
        """Read a required list of regular expressions, possibly empty."""
        compiled: list[re.Pattern[str]] = []
        for text in self.strings(key):
            try:
                compiled.append(re.compile(text))
            except re.error as error:
                raise self._error(key, f"invalid regular expression {text!r}: {error}") from error
        return tuple(compiled)

    def section(self, key: str) -> "Fields | None":
        """Read a nested mapping as a reader of its own, or None when the key is absent or null."""
        value = self._get(key)
        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise self._error(key, "expected a mapping, or null to disable the construct")
        path = f"{self._path}.{key}" if self._path else key
        return Fields(value, path, self._origin)

    def finish(self) -> None:
        """
        Reject every key of the mapping left unread.

        Raises
        ------
        SyntaxFileError
            If the mapping holds a key that no reader read.
        """
        unknown = sorted(set(self._data) - self._read)
        if unknown:
            raise self._error(unknown[0], "unknown key")


@dataclass(frozen=True)
class SyntaxDocument:
    """
    Header and body of one syntax file.

    Attributes
    ----------
    source_type : str
        Name of the source type whose segmenter reads the body.
    name : str
        Name of the syntax.
    body : Fields
        Reader of the keys of the file outside its header.
    """

    source_type: str
    name: str
    body: Fields


def read_syntax_document(text: str, origin: str) -> SyntaxDocument:
    """
    Parse the text of a syntax file.

    Parameters
    ----------
    text : str
        Content of the syntax file.
    origin : str
        Name of the file, used in error messages.

    Returns
    -------
    SyntaxDocument
        Header and body of the file.

    Raises
    ------
    SyntaxFileError
        If the text is not a YAML mapping, or its header is missing or holds another version.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise SyntaxFileError(f"{origin}: invalid YAML: {error}") from error
    if not isinstance(data, Mapping):
        raise SyntaxFileError(f"{origin}: a syntax file holds a mapping")
    version = data.get("syntax_version")
    if version != SYNTAX_VERSION:
        raise SyntaxFileError(f"{origin}: syntax_version {version!r}, expected {SYNTAX_VERSION}")
    header = Fields({key: data.get(key) for key in HEADER_KEYS}, "", origin)
    source_type = header.string("source_type")
    name = header.string("name")
    body = {key: value for key, value in data.items() if key not in HEADER_KEYS}
    return SyntaxDocument(source_type, name, Fields(body, "", origin))


def load_syntax_document(path: Path) -> SyntaxDocument:
    """
    Read and parse a syntax file.

    Raises
    ------
    SyntaxFileError
        If the file cannot be read, or its content is invalid.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise SyntaxFileError(f"{path}: cannot read the syntax file: {error}") from error
    return read_syntax_document(text, str(path))


def packaged_syntax_document(name: str) -> SyntaxDocument:
    """
    Read a syntax file shipped with Merismos, by its file name without extension.

    Raises
    ------
    SyntaxFileError
        If no packaged syntax carries the name.
    """
    folder = resources.files(__package__).joinpath(PACKAGED_SYNTAXES)
    resource = folder.joinpath(f"{name}.yml")
    if not resource.is_file():
        raise SyntaxFileError(f"no packaged syntax named {name!r}")
    return read_syntax_document(
        resource.read_text(encoding="utf-8"), f"{PACKAGED_SYNTAXES}/{name}.yml"
    )
