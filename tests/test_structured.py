"""Tests of the extraction of prose strings from YAML, Python and commit sources."""

import inspect
from pathlib import Path

import pytest
import yaml

from merismos import Segmentation, segment
from merismos.errors import SourceSyntaxError, SyntaxFileError
from merismos.registry import default_registry


def _assert_pieces_verbatim(segmentation: Segmentation) -> None:
    """Every piece of every decoded string reproduces the source text it maps to."""
    for region in segmentation:
        assert region.string is not None
        for piece in region.string.pieces:
            value = region.string.value[piece.value_start : piece.value_start + piece.length]
            assert (
                value == segmentation.source[piece.source_start : piece.source_start + piece.length]
            )


def _syntax(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "syntax.yml"
    path.write_text(text, encoding="utf-8")
    return path


# --- YAML ---------------------------------------------------------------------------------------

YAML_SCALARS = {
    "plain": "a: plain  words\n",
    "plain-multiline": "a: one\n  two\n\n  three\n",
    "single": "a: 'it''s'\n",
    "single-folded": "a: 'one\n  two\n\n  three'\n",
    "double-escapes": 'a: "t\\tn\\nu\\u00e9x\\x41"\n',
    "double-joined": 'a: "one \\\n  two"\n',
    "literal": "a: |\n  one\n   two\n\n",
    "literal-keep": "a: |+\n  one\n\n\nb: x\n",
    "literal-strip-indent": "a: |-2\n    one\n",
    "folded": "a: >\n  one\n  two\n\n  three\n   four\n",
    "crlf": "a: |\r\n  one\r\n  two\r\n",
    "flow": "a: [x, 'y z', \"w\"]\n",
    "sequence-block": "- |\n  one\n- >-\n  two\n  three\n",
    "unicode": "a: café ✓ 𝔸\n",
}


@pytest.mark.parametrize("text", YAML_SCALARS.values(), ids=YAML_SCALARS.keys())
def test_yaml_values_decode_as_pyyaml_reads_them(text: str) -> None:
    """Each string scalar decodes to the value of PyYAML, with verbatim pieces."""
    segmentation = segment(text, "yaml")
    values = [region.string.value for region in segmentation.select(["yaml-value"])]
    expected: list[str] = []

    def collect(node: object) -> None:
        if isinstance(node, str):
            expected.append(node)
        elif isinstance(node, dict):
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for item in node:
                collect(item)

    collect(yaml.safe_load(text))
    assert values == expected
    _assert_pieces_verbatim(segmentation)


def test_yaml_escape_maps_to_its_backslash() -> None:
    text = 'a: "x\\ty"\n'
    (region,) = segment(text, "yaml")
    assert region.string is not None
    assert text[region.string.to_source(1)] == "\\"
    assert text[region.string.to_source(2)] == "y"


def test_yaml_attributes_name_the_pointer_style_and_document() -> None:
    text = "a/b:\n  c~d: 'x'\n---\n- y\n"
    regions = segment(text, "yaml").regions
    assert [dict(region.attributes) for region in regions] == [
        {"pointer": "/a~1b/c~0d", "style": "single-quoted", "document": 0},
        {"pointer": "/0", "style": "plain", "document": 1},
    ]


def test_yaml_non_string_scalars_are_left_out() -> None:
    assert len(segment("a: 1\nb: true\nc: null\nd: 2024-01-01\n", "yaml")) == 0


def test_yaml_comments_skip_markers_inside_scalars() -> None:
    text = "# head\na: 'x # y'  # tail\nb: c#d\n"
    comments = segment(text, "yaml").select(["yaml-comment"])
    assert [region.string.value for region in comments if region.string] == [" head", " tail"]


def test_yaml_syntax_selects_roles(tmp_path: Path) -> None:
    path = _syntax(
        tmp_path,
        "syntax_version: 1\nsource_type: yaml\nname: keys\n"
        "mapping_values: false\nsequence_items: false\nmapping_keys: true\ncomments: false\n",
    )
    regions = default_registry().segmenter("yaml", path).segment("a: x # c\nb: [y]\n")
    assert [region.string.value for region in regions if region.string] == ["a", "b"]


def test_yaml_invalid_source_is_reported() -> None:
    with pytest.raises(SourceSyntaxError):
        segment("a: [unclosed\n", "yaml")


# --- Python -------------------------------------------------------------------------------------

PYTHON_SOURCE = '''"""Module docstring."""

# A comment ✓


class Owner:
    r"""Raw \\n kept."""

    def method(self):
        """
        Summary line.

            Indented \\t escape and \\N{GREEK SMALL LETTER ALPHA}.
        """
        return "not a docstring"  # trailing


async def run():
    "Implicit" " concatenation."
'''


def test_python_docstrings_decode_with_their_owners() -> None:
    regions = segment(PYTHON_SOURCE, "python").select(["python-docstring"])
    assert [(region.attributes["owner"], region.attributes["name"]) for region in regions] == [
        ("module", ""),
        ("class", "Owner"),
        ("function", "Owner.method"),
        ("function", "run"),
    ]
    assert regions[2].string is not None
    raw = "\n        Summary line.\n\n            Indented \t escape and α.\n        "
    assert regions[2].string.value == inspect.cleandoc(raw)
    assert regions[3].string is not None and regions[3].string.value == "Implicit concatenation."


def test_python_pieces_are_verbatim() -> None:
    _assert_pieces_verbatim(segment(PYTHON_SOURCE, "python"))


def test_python_comments_keep_their_text_after_the_marker() -> None:
    comments = segment(PYTHON_SOURCE, "python").select(["python-comment"])
    assert [region.string.value for region in comments if region.string] == [
        " A comment ✓",
        " trailing",
    ]


def test_python_columns_count_code_points_after_non_ascii_text() -> None:
    text = 'x = "é"; y = 1\ndef f(é=1): """Doc after ✓ é."""\n'
    (region,) = segment(text, "python").select(["python-docstring"])
    assert region.string is not None and region.string.value == "Doc after ✓ é."
    _assert_pieces_verbatim(segment(text, "python"))


def test_python_crlf_source_decodes() -> None:
    text = 'def f():\r\n    """One\r\n\r\n    two."""\r\n'
    (region,) = segment(text, "python").select(["python-docstring"])
    assert region.string is not None and region.string.value == "One\n\ntwo."
    _assert_pieces_verbatim(segment(text, "python"))


def test_python_dedent_none_keeps_the_raw_value(tmp_path: Path) -> None:
    path = _syntax(
        tmp_path,
        "syntax_version: 1\nsource_type: python\nname: raw\n"
        "docstring_owners: [function]\ndedent: none\ncomments: false\n",
    )
    regions = default_registry().segmenter("python", path).segment(PYTHON_SOURCE)
    assert [region.attributes["name"] for region in regions] == ["Owner.method", "run"]
    assert regions[0].string is not None and regions[0].string.value.startswith("\n        Summary")


def test_python_unknown_owner_is_rejected(tmp_path: Path) -> None:
    path = _syntax(
        tmp_path,
        "syntax_version: 1\nsource_type: python\nname: x\n"
        "docstring_owners: [method]\ndedent: none\ncomments: false\n",
    )
    with pytest.raises(SyntaxFileError, match="method"):
        default_registry().segmenter("python", path)


def test_python_invalid_source_is_reported() -> None:
    with pytest.raises(SourceSyntaxError):
        segment("def f(:\n", "python")


# --- commit messages ----------------------------------------------------------------------------

MESSAGE = (
    "feat: Add x\n"
    "######\n"
    "\n"
    "Body one   \n"
    "line two\n"
    "\n"
    "\n"
    "# a comment\n"
    "Second paragraph\n"
    "\n"
    "Signed-off-by: A <a@b>\n"
    "Co-Authored-By: B\n"
    "  continued\n"
)


def test_commit_subject_and_body_leave_out_comments_and_trailers() -> None:
    subject, body = segment(MESSAGE, "commit").regions
    assert subject.string is not None and subject.string.value == "feat: Add x"
    assert body.string is not None and body.string.value == "Body one\nline two\n\nSecond paragraph"
    _assert_pieces_verbatim(segment(MESSAGE, "commit"))


def test_commit_syntax_keeps_blank_runs_and_first_line(tmp_path: Path) -> None:
    path = _syntax(
        tmp_path,
        "syntax_version: 1\nsource_type: commit\nname: x\ncomment_character: null\n"
        "strip_trailing_whitespace: false\ncollapse_blank_lines: false\nsubject: first-line\n"
        "trailer_pattern: null\n",
    )
    regions = default_registry().segmenter("commit", path).segment("Subject\nmore\n\n\n\nEnd   \n")
    assert [region.string.value for region in regions if region.string] == [
        "Subject",
        "more\n\n\n\nEnd   ",
    ]


def test_commit_without_body_has_a_subject_only() -> None:
    assert [region.kind for region in segment("fix: One line\n", "commit")] == ["commit-subject"]
