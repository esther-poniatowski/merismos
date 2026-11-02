"""
Plain-data form of regions and segmentations, as the conformance files and the command line write
them.

A region becomes a mapping with the keys `kind` and `range`, then `content`, and, when they are
not empty, `gaps`, `attributes`, `value` and `pieces`. A span becomes a list of two offsets, and a
piece a list of three integers. The form is the one of the contract, so that a consumer written in
another language can read the output of the command line.

Functions
---------
region_to_data(region) -> dict
    Convert a region to plain data.
region_from_data(data) -> Region
    Rebuild a region from plain data.
segmentation_to_data(segmentation) -> dict
    Convert a segmentation to plain data.
"""

from typing import Mapping, Sequence

from .model import AttributeValue, DecodedString, Piece, Region, Segmentation, Span

RegionData = dict[str, object]
"""Plain-data form of one region."""


def _span(data: object, key: str) -> Span:
    """Rebuild a span from a list of two offsets."""
    if (
        not isinstance(data, Sequence)
        or len(data) != 2
        or not all(isinstance(item, int) for item in data)
    ):
        raise ValueError(f"{key}: expected a list of two offsets")
    return Span(data[0], data[1])


def region_to_data(region: Region) -> RegionData:
    """
    Convert a region to plain data.

    Examples
    --------
    >>> region_to_data(Region("inline-math", Span(4, 9), Span(5, 8)))
    {'kind': 'inline-math', 'range': [4, 9], 'content': [5, 8]}
    """
    data: RegionData = {
        "kind": region.kind,
        "range": [region.range.start, region.range.end],
        "content": None if region.content is None else [region.content.start, region.content.end],
    }
    if region.gaps:
        data["gaps"] = [[gap.start, gap.end] for gap in region.gaps]
    if region.attributes:
        data["attributes"] = dict(region.attributes)
    if region.string is not None:
        data["value"] = region.string.value
        data["pieces"] = [
            [piece.value_start, piece.source_start, piece.length] for piece in region.string.pieces
        ]
    return data


def region_from_data(data: Mapping[str, object]) -> Region:
    """
    Rebuild a region from plain data.

    Raises
    ------
    ValueError
        If a key is missing or holds a value of the wrong form.
    """
    kind = data.get("kind")
    if not isinstance(kind, str):
        raise ValueError("kind: expected a string")
    content = data.get("content")
    gaps = data.get("gaps", [])
    attributes = data.get("attributes", {})
    if not isinstance(gaps, Sequence) or not isinstance(attributes, Mapping):
        raise ValueError("gaps and attributes: expected a list and a mapping")
    string = None
    if "value" in data:
        value = data["value"]
        pieces = data.get("pieces", [])
        if not isinstance(value, str) or not isinstance(pieces, Sequence):
            raise ValueError("value and pieces: expected a string and a list")
        string = DecodedString(value, tuple(Piece(*_piece(item)) for item in pieces))
    typed_attributes: dict[str, AttributeValue] = {}
    for name, item in attributes.items():
        if not isinstance(name, str) or not isinstance(item, (str, int, bool, type(None))):
            raise ValueError(f"attributes: unsupported value for {name!r}")
        typed_attributes[name] = item
    return Region(
        kind,
        _span(data.get("range"), "range"),
        None if content is None else _span(content, "content"),
        tuple(_span(gap, "gaps") for gap in gaps),
        typed_attributes,
        string,
    )


def _piece(data: object) -> tuple[int, int, int]:
    """Rebuild the three integers of a piece from a list."""
    if (
        not isinstance(data, Sequence)
        or len(data) != 3
        or not all(isinstance(item, int) for item in data)
    ):
        raise ValueError("pieces: expected lists of three integers")
    return data[0], data[1], data[2]


def segmentation_to_data(segmentation: Segmentation) -> dict[str, object]:
    """Convert a segmentation to plain data: its source type and its regions."""
    return {
        "source_type": segmentation.source_type,
        "regions": [region_to_data(region) for region in segmentation.regions],
    }
