"""
Segmenter of YAML sources: the string scalars and the comments of every document.

A region of a string scalar carries its decoded value with its pieces, and three attributes: the
JSON Pointer of the scalar in its document, its style, and the index of its document. The syntax
selects the roles of the scalars to extract: values of mappings, items of sequences, keys of
mappings, and comments.

Classes
-------
YamlSyntax
    Roles of the strings that a YAML segmenter extracts.
YamlSegmenter
    Segmenter of YAML sources under one syntax.

Functions
---------
parse_yaml_syntax(name, fields) -> YamlSyntax
    Parse the body of a YAML syntax file.
"""

from dataclasses import dataclass

import yaml

from ..errors import SourceSyntaxError
from ..model import AttributeValue, DecodedString, Piece, Region, Segmentation, Span
from ..syntax import Fields
from . import kinds
from .base import StructuredSegmenter
from .yaml_scalars import ScalarDecoder

STRING_TAG = "tag:yaml.org,2002:str"
"""Tag that the resolver of PyYAML gives to a string scalar."""

COMMENT_MARKER = "#"
"""Character opening a YAML comment after a space or at the start of a line."""

STYLE_NAMES = {
    None: "plain",
    "'": "single-quoted",
    '"': "double-quoted",
    "|": "literal",
    ">": "folded",
}
"""Name of each style of scalar, as a region attribute reports it."""


@dataclass(frozen=True)
class YamlSyntax:
    """
    Roles of the strings that a YAML segmenter extracts.

    Attributes
    ----------
    mapping_values : bool
        Whether the values of mappings, and a scalar forming a whole document, are extracted.
    sequence_items : bool
        Whether the items of sequences are extracted.
    mapping_keys : bool
        Whether the keys of mappings are extracted.
    comments : bool
        Whether comments are extracted.
    """

    mapping_values: bool
    sequence_items: bool
    mapping_keys: bool
    comments: bool


def parse_yaml_syntax(name: str, fields: Fields) -> YamlSyntax:
    """Parse the body of a YAML syntax file, rejecting unknown keys."""
    del name  # The YAML syntax has no construct whose errors would cite the name.
    syntax = YamlSyntax(
        mapping_values=fields.boolean("mapping_values"),
        sequence_items=fields.boolean("sequence_items"),
        mapping_keys=fields.boolean("mapping_keys"),
        comments=fields.boolean("comments"),
    )
    fields.finish()
    return syntax


def _pointer_token(key: yaml.Node) -> str:
    """Escape a key as a token of a JSON Pointer."""
    text = key.value if isinstance(key, yaml.ScalarNode) else "?"
    return str(text).replace("~", "~0").replace("/", "~1")


class YamlSegmenter(StructuredSegmenter[YamlSyntax]):
    """
    Segmenter of YAML sources under one syntax.

    Parameters
    ----------
    syntax : YamlSyntax
        Roles of the strings to extract.
    source_type : str
        Name of the source type reported in each segmentation.
    """

    def segment(self, source: str) -> Segmentation:
        """
        Segment a YAML source.

        Raises
        ------
        SourceSyntaxError
            If the source does not parse as YAML.
        DecodingError
            If a scalar decodes to another value than the one read by PyYAML.
        """
        try:
            documents = list(yaml.compose_all(source, Loader=yaml.SafeLoader))
            tokens = list(yaml.scan(source, Loader=yaml.SafeLoader))
        except yaml.YAMLError as error:
            raise SourceSyntaxError(f"invalid YAML: {error}") from error
        walk = _Walk(self._syntax, source)
        for index, root in enumerate(documents):
            if root is not None:
                walk.node(root, "", -1, "value", index)
        regions = walk.regions
        if self._syntax.comments:
            regions.extend(_comments(source, tokens))
        return self._segmentation(source, regions)


class _Walk:
    """Traversal of the nodes of a source, collecting the selected string scalars."""

    def __init__(self, syntax: YamlSyntax, source: str) -> None:
        self._syntax = syntax
        self._source = source
        self._decoder = ScalarDecoder(source)
        self._seen: set[int] = set()
        self.regions: list[Region] = []

    def _selected(self, role: str) -> bool:
        """Whether the syntax extracts the scalars of a role."""
        return {
            "value": self._syntax.mapping_values,
            "item": self._syntax.sequence_items,
            "key": self._syntax.mapping_keys,
        }[role]

    def node(
        self, node: yaml.Node, pointer: str, parent_indent: int, role: str, document: int
    ) -> None:
        """Visit a node once, an alias reaching the same node again adding nothing."""
        if id(node) in self._seen:
            return
        self._seen.add(id(node))
        if isinstance(node, yaml.ScalarNode):
            if node.tag == STRING_TAG and self._selected(role):
                self.regions.append(self._scalar(node, pointer, parent_indent, document))
        elif isinstance(node, yaml.MappingNode):
            indent = node.start_mark.column
            for key, value in node.value:
                self.node(key, pointer, indent, "key", document)
                self.node(value, f"{pointer}/{_pointer_token(key)}", indent, "value", document)
        elif isinstance(node, yaml.SequenceNode):
            indent = node.start_mark.column
            for index, item in enumerate(node.value):
                self.node(item, f"{pointer}/{index}", indent, "item", document)

    def _scalar(
        self, node: yaml.ScalarNode, pointer: str, parent_indent: int, document: int
    ) -> Region:
        """Build the region of a string scalar, with its decoded value and pieces."""
        start, end = node.start_mark.index, node.end_mark.index
        traced = self._decoder.decode(node.style, start, end, parent_indent)
        attributes: dict[str, AttributeValue] = {
            "pointer": pointer,
            "style": STYLE_NAMES[node.style],
            "document": document,
        }
        return Region(
            kinds.YAML_VALUE,
            Span(start, end),
            attributes=attributes,
            string=traced.decoded(self._source, expected=node.value),
        )


def _comments(source: str, tokens: list[yaml.Token]) -> list[Region]:
    """Find the comments of a source: a marker after a space or at a line start, outside scalars."""
    scalars = [
        Span(token.start_mark.index, token.end_mark.index)
        for token in tokens
        if isinstance(token, yaml.ScalarToken)
    ]
    regions: list[Region] = []
    line_start = 0
    for line in source.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        for column, character in enumerate(content):
            position = line_start + column
            if character != COMMENT_MARKER or (column and content[column - 1] not in " \t"):
                continue
            if any(scalar.start <= position < scalar.end for scalar in scalars):
                continue
            end = line_start + len(content)
            value = source[position + 1 : end]
            pieces = (Piece(0, position + 1, len(value)),) if value else ()
            regions.append(
                Region(kinds.YAML_COMMENT, Span(position, end), string=DecodedString(value, pieces))
            )
            break
        line_start += len(line)
    return regions
