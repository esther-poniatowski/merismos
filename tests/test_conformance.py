"""Tests of the Markdown segmenter against the published conformance cases."""

from pathlib import Path

import pytest

from merismos.conformance import Case, check_case, load_cases
from merismos.registry import default_registry

CASES_FILE = Path(__file__).resolve().parent.parent / "specs" / "conformance" / "markdown.yml"
CASES = load_cases(CASES_FILE)


@pytest.mark.parametrize("case", CASES, ids=[case.identifier for case in CASES])
def test_case_conforms(case: Case) -> None:
    """Each case returns exactly its expected regions."""
    mismatch = check_case(case, default_registry().segmenter(case.source_type))
    assert mismatch is None, mismatch.describe()


@pytest.mark.parametrize("case", CASES, ids=[case.identifier for case in CASES])
def test_case_regions_form_a_forest(case: Case, assert_forest) -> None:
    """The regions of each case satisfy the invariants of the contract."""
    assert_forest(default_registry().segmenter(case.source_type).segment(case.text))


def test_identifiers_are_unique() -> None:
    """No two cases share an identifier, so a mismatch names one case."""
    identifiers = [case.identifier for case in CASES]
    assert len(identifiers) == len(set(identifiers))


def test_a_wrong_expectation_is_reported() -> None:
    """A case whose expected regions differ from the returned ones yields a mismatch."""
    case = CASES[0]
    wrong = Case(case.identifier, case.source_type, None, None, case.text, ())
    mismatch = check_case(wrong, default_registry().segmenter(case.source_type))
    assert mismatch is not None
    assert "region 0" in mismatch.describe()
