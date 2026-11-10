---
tags:
  - specification
index: "[Merismos documentation](docs/_index.md)"
aliases:
  - Syntax files
---
# Syntax files

A syntax file declares the grammar under which Merismos segments one source type: the delimiters of each construct, the constructs enabled, and the strings to extract. A consumer changes a dialect by passing its own syntax file, without code. Merismos ships one syntax per source type in the package folder `syntaxes`, and the file `syntaxes/defaults.yml` names the syntax read when a consumer passes none.

## Header

Three keys open every syntax file, and every other key belongs to its source type:

| Key | Value |
| --- | --- |
| `syntax_version` | the version of the layout of syntax files, 1 for this release |
| `source_type` | the source type whose segmenter reads the file |
| `name` | the name of the syntax, such as `obsidian` |

Merismos rejects a file holding an unknown key, a value of the wrong type, or a `source_type` other than the requested type. Each error names the file and the key path of the value.

## Markdown

A section of a Markdown syntax describes one construct, and a section set to `null` disables it:

| Key | Value | Packaged Obsidian value |
| --- | --- | --- |
| `tab_width` | columns between two tab stops | 4 |
| `block_indent` | columns admitted before the marker of a block | 3 |
| `frontmatter.fence` | the line opening and closing the frontmatter | `---` |
| `fences.characters`, `fences.minimum_length` | characters of a fence, and the shortest run opening one | `` ` `` and `~`, 3 |
| `fences.info_excludes_fence` | fence characters that the info string of their fence may not hold | `` ` `` |
| `indented_code.indent` | columns of indentation opening indented code | 4 |
| `headings.marker`, `headings.maximum_level` | character of a heading marker, and the longest run of it | `#`, 6 |
| `quotations.marker`, `quotations.spacing` | character opening each line of a quotation, and the columns of space after it that belong to the marker | `>`, 1 |
| `quotations.callout` | `opening`, `closing`, `type_pattern` (a regular expression) and `fold_signs` of a callout, or `null`; a fold sign right after the closing delimiter becomes the attribute `fold` | `[!`, `]`, `[A-Za-z0-9_-]+`, `+` and `-` |
| `lists.bullets`, `lists.ordered_delimiters` | characters of a bullet, and of the delimiter after an ordinal | `-`, `*`, `+`; `.`, `)` |
| `lists.maximum_digits`, `lists.maximum_spacing` | digits of an ordinal, and columns of spacing that still set the content column | 9, 4 |
| `thematic_breaks.characters`, `thematic_breaks.minimum_count` | characters of a thematic break, and the fewest of them | `-`, `*`, `_`; 3 |
| `setext_underlines` | characters whose run under a paragraph closes it | `=`, `-` |
| `code_span` | character whose runs delimit a code span, or `null` | `` ` `` |
| `code_span_shorter_closing` | whether, when no run of the width of the opening run follows it, the first narrower run closes a code span, the excess characters of the opening run staying literal | true |
| `code_span_over_links` | whether a code span crossing the text of a link prevails over the link, as in CommonMark; a code span inside the text holds its brackets either way | false |
| `math.display`, `math.inline` | delimiters of display and inline mathematics, each possibly `null` | `$$`, `$` |
| `math.inline_spans_lines` | whether inline mathematics may cross a line break | false |
| `math.display_spans_blank_lines` | whether a blank line inside display mathematics keeps it open | true |
| `math.display_unclosed_runs_to_end` | whether an unclosed display delimiter opening a line opens a formula running to the end of its container; an unclosed delimiter elsewhere, or every unclosed delimiter when false, is literal | true |
| `links.markdown` | `text_opening`, `text_closing`, `destination_opening`, `destination_closing`, `destination_brackets` (two characters) and `title_delimiters` (pairs of characters) of a Markdown link, or `null` | `[`, `]`, `(`, `)`; `<` and `>`; `""`, `''` and `()` |
| `links.embeds_in_text` | whether the text of a Markdown link may hold embeds | true |
| `links.wikilink` | `opening`, `closing` and `alias_separator` of a wikilink, `escaped_separator`, whether an escaped separator still separates the alias, and the optional `excluded`, the characters that its destination cannot hold; or `null` | `[[`, `]]`, `|`; true; none |
| `links.embed_prefix` | prefix turning a link into an embed, or `null` | `!` |
| `escape.character`, `escape.escapable` | escape character, and the characters it escapes | `\`, the ASCII punctuation |

The packaged Obsidian syntax is the file `syntaxes/markdown-obsidian.yml`. ^obsidian

## YAML

A YAML syntax selects the roles of the strings to extract:

| Key | Value | Packaged value |
| --- | --- | --- |
| `mapping_values` | whether the values of mappings, and a scalar forming a whole document, are extracted | true |
| `sequence_items` | whether the items of sequences are extracted | true |
| `mapping_keys` | whether the keys of mappings are extracted | false |
| `comments` | whether comments are extracted | true |
| `comment_exclusions` | regular expressions of the comment texts left out, each matched at the start of the text after `#` | the directive `yaml-language-server:` |

## Python

A Python syntax selects the docstrings to extract and their dedent:

| Key | Value | Packaged value |
| --- | --- | --- |
| `docstring_owners` | kinds of owners whose docstrings are extracted, among `module`, `class` and `function` | all three |
| `dedent` | `cleandoc`, the dedent of `inspect.cleandoc`, or `none` | `cleandoc` |
| `comments` | whether comments are extracted | true |
| `comment_exclusions` | regular expressions of the comment texts left out, each matched at the start of the text after `#` | a shebang, a coding declaration, and the directives of type checkers, linters and formatters |

## Commit messages

A commit syntax states the cleanup of a message before it is read, as the cleanup mode of Git does:

| Key | Value | Packaged Git value |
| --- | --- | --- |
| `comment_character` | character opening a comment line, or `null` | `#` |
| `strip_trailing_whitespace` | whether the whitespace ending a line is left out | true |
| `collapse_blank_lines` | whether a run of blank lines reads as one | true |
| `subject` | `first-paragraph`, as Git reads the subject, or `first-line` | `first-paragraph` |
| `trailer_pattern` | regular expression matching a trailer line, or `null` when no final paragraph is set apart | `[A-Za-z0-9][A-Za-z0-9-]*: ` |
| `scissors_pattern` | regular expression matching the whole line that cuts the message, or `null`; the line and every later line are left out | `# -+ >8 -+`, as `git commit --verbose` writes it |
