"""
Conformance cases: texts with the regions that a segmenter must return for them.

A conformance file names its contract and lists cases. Each case holds an identifier, its source
type, the version of Obsidian in which its reading was observed (null before any observation),
an optional note, the text and the expected regions in plain-data form.

Classes
-------
Case
    One conformance case.
Mismatch
    Difference between the expected and the returned regions of one case.

Functions
---------
load_cases(path) -> tuple[Case, ...]
    Read the cases of a conformance file.
check_case(case, segmenter) -> Mismatch | None
    Segment the text of a case and compare the result with its expected regions.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import yaml

from .errors import MerismosError
from .registry import Segmenter
from .serialization import RegionData, region_to_data


@dataclass(frozen=True)
class Case:
    """
    One conformance case.

    Attributes
    ----------
    identifier : str
        Name of the case.
    source_type : str
        Source type of the text.
    observed : str | None
        Version of Obsidian in which the reading of the case was observed, or None.
    note : str | None
        Point of reading fixed by the case.
    text : str
        Source to segment.
    regions : tuple[RegionData, ...]
        Expected regions, in plain-data form.
    """

    identifier: str
    source_type: str
    observed: str | None
    note: str | None
    text: str
    regions: tuple[RegionData, ...]


@dataclass(frozen=True)
class Mismatch:
    """
    Difference between the expected and the returned regions of one case.

    Attributes
    ----------
    case : Case
        Case whose regions differ.
    returned : tuple[RegionData, ...]
        Regions returned by the segmenter, in plain-data form.
    """

    case: Case
    returned: tuple[RegionData, ...]

    def describe(self) -> str:
        """Describe the first region that differs, with its index."""
        expected, returned = self.case.regions, self.returned
        for index in range(max(len(expected), len(returned))):
            left = expected[index] if index < len(expected) else None
            right = returned[index] if index < len(returned) else None
            if left != right:
                return f"{self.case.identifier}: region {index}: expected {left}, returned {right}"
        return f"{self.case.identifier}: regions differ"


def _case(data: object, origin: str) -> Case:
    if not isinstance(data, Mapping):
        raise MerismosError(f"{origin}: each case is a mapping")
    identifier, source_type, text = data.get("id"), data.get("source"), data.get("text")
    regions = data.get("regions")
    if not (isinstance(identifier, str) and isinstance(source_type, str) and isinstance(text, str)):
        raise MerismosError(f"{origin}: a case holds the strings id, source and text")
    if not isinstance(regions, Sequence) or not all(
        isinstance(region, Mapping) for region in regions
    ):
        raise MerismosError(f"{origin}: case {identifier}: regions is a list of mappings")
    observed, note = data.get("observed"), data.get("note")
    return Case(
        identifier,
        source_type,
        None if observed is None else str(observed),
        None if note is None else str(note),
        text,
        tuple(dict(region) for region in regions),
    )


def load_cases(path: Path) -> tuple[Case, ...]:
    """
    Read the cases of a conformance file.

    Raises
    ------
    MerismosError
        If the file cannot be read or holds no list of cases.
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise MerismosError(f"{path}: cannot read the conformance file: {error}") from error
    cases = data.get("cases") if isinstance(data, Mapping) else None
    if not isinstance(cases, Sequence):
        raise MerismosError(f"{path}: expected a list under cases")
    return tuple(_case(item, str(path)) for item in cases)


def check_case(case: Case, segmenter: Segmenter) -> Mismatch | None:
    """Segment the text of a case, and return the mismatch with its expected regions, if any."""
    returned = tuple(region_to_data(region) for region in segmenter.segment(case.text))
    if returned == case.regions:
        return None
    return Mismatch(case, returned)
