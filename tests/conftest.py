"""Pytest configuration and shared fixtures for merismos tests."""

from typing import Callable

import pytest

from merismos.model import Region, Segmentation
from merismos.markdown.kinds import OPAQUE_KINDS


def _assert_forest(segmentation: Segmentation) -> None:
    """
    Assert the invariants of the contract on a segmentation.

    The regions are sorted by start, then by end decreasing; two regions are disjoint or nested;
    an opaque region contains no region; every content lies in its range and every gap in its
    content.
    """
    regions = segmentation.regions
    keys = [(region.range.start, -region.range.end) for region in regions]
    assert keys == sorted(keys), "regions out of order"
    open_regions: list[Region] = []
    for region in regions:
        while open_regions and not open_regions[-1].range.contains(region.range):
            open_regions.pop()
        if open_regions:
            parent = open_regions[-1]
            assert parent.kind not in OPAQUE_KINDS, f"{region.kind} nested in opaque {parent.kind}"
        for other in open_regions:
            assert other.range.contains(region.range)
        for earlier in regions[: regions.index(region)]:
            if earlier.range.overlaps(region.range):
                assert earlier.range.contains(region.range) or region.range.contains(
                    earlier.range
                ), f"{earlier.kind} {earlier.range} and {region.kind} {region.range} overlap"
        open_regions.append(region)
        if region.content is not None:
            assert region.range.contains(region.content)
            for gap in region.gaps:
                assert region.content.contains(gap)


@pytest.fixture
def assert_forest() -> Callable[[Segmentation], None]:
    """Checker of the invariants of the contract on a segmentation."""
    return _assert_forest
