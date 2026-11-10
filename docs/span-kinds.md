---
tags:
  - specification
index: "[Merismos documentation](docs/_index.md)"
aliases:
  - Span kinds
---
# Span kinds

Merismos segments a source into regions, each typed by a span kind and located by exact offsets. This specification defines the contract `merismos:span-kinds@1`: the regions returned to a consumer for a source. The [conformance cases for Markdown](../specs/conformance/markdown.yml) fix the regions expected for given texts, the [syntax files](syntax-files.md) fix the delimiters of each construct, and the [segmentation decision](adr/segmentation-contract.md) records the reason for each choice.

## Source types

A consumer passes each source with its type:

- `markdown`, a Markdown or Obsidian note;
- `yaml`, a YAML file;
- `python`, a Python module;
- `commit`, a commit message.

Merismos never infers the type from a file name, since the consumer maps its files to types in its own configuration. The consumer also selects there the kinds to read. ^source-types

A source is a string of Unicode code points, read without any change. In particular, line endings keep their form: a line ends at `\n`, `\r\n` or `\r`, and a YAML line also ends at `\x85`, `\u2028` or `\u2029`, as YAML admits them.

## Regions

Every region holds five fields, of which `gaps` and `attributes` are omitted when they are empty:

| Field | Value |
| --- | --- |
| `kind` | the span kind of the region, among the kinds listed below |
| `range` | the start and end offsets of the whole construct, delimiters included |
| `content` | the start and end offsets of the part between the delimiters, or null for a kind divided into child regions or decoded into a string |
| `gaps` | the ranges inside the content belonging to a container prefix |
| `attributes` | the attributes of the kind |

A region of a YAML, Python or commit source also holds the two fields stated under [decoded strings](#^pieces).

Every range is half-open, and every offset counts code points from the start of the source, beginning at 0. ^offsets

## Nesting and order

Two regions are either disjoint or nested, one range containing the other. No construct opens inside a region of an *opaque* kind, so an opaque region is always a leaf. Merismos returns the regions sorted by start, then by end in decreasing order, and, for equal ranges, the enclosing region first. Therefore, each container precedes the regions nested in it. ^nesting

## Markdown kinds

The kinds of a Markdown source are the following:

| Kind | Construct | Content | Opaque | Attributes |
| --- | --- | --- | --- | --- |
| `frontmatter` | the YAML block opening the source | the lines between the two fences | yes | none |
| `fenced-code` | a fenced code block | the lines between the fences | yes | `info`: the info string, possibly empty |
| `indented-code` | a code block written by indentation | the text after the indentation of its first line | yes | none |
| `inline-code` | a code span | the text between the backtick strings | yes | none |
| `display-math` | mathematics delimited by the display delimiter | the TeX between the delimiters | yes | none |
| `inline-math` | mathematics delimited by the inline delimiter | the TeX between the delimiters | yes | none |
| `heading` | a heading opened by a run of markers | the text after the markers and their spaces, without the closing run | no | `level`: the number of markers |
| `quotation` | a block quote, a callout included | the text after the first marker, to the end of the range | no | `callout`: the type of a callout as written, or null; `fold`: the fold sign of a callout, or null |
| `link` | a Markdown link or a wikilink, an embed included | null, since its parts are child regions | no | `syntax`: `markdown` or `wiki`; `embed`: true for an embed |
| `link-text` | the text displayed by a link | the text itself | no | none |
| `link-destination` | the destination of a link | the destination, without angle brackets | yes | none |

The *block* kinds are the kinds whose construct occupies whole lines: the code blocks, the frontmatter, the headings and the quotations. A block starts at its first marker, or at its indentation for indented code, after the prefixes of its containers. A block ends at the end of its last line, before the line ending. ^block-range

The *fenced* kinds are `frontmatter` and `fenced-code`. The content of a fenced kind starts with its first inner line and stops at the start of its closing line, so it holds the line ending of its last inner line. When the fence is never closed, the content runs to the end of the range, before the last line ending. ^fenced-content

A *container prefix* is the part of a line consumed before the content of a block. Three blocks have one:

- a quotation, whose prefix is its marker with at most one following space;
- a list item, whose prefix on each line after its first is the indentation required for its content: the width of its marker and of the spaces following it, as CommonMark sets it [macfarlane2024];
- an indented code block, whose prefix on each line after its first is its indentation.

Indentation beyond the required width belongs to the content. A lazy continuation line of a quotation, written without its marker, has no prefix. A region lists as gaps every prefix crossed by its content, whether the prefix belongs to the region itself or to an enclosing container. ^gaps

## Reading of a Markdown source

Merismos reads each construct as Obsidian reads it. Under the [packaged Obsidian syntax](syntax-files.md#^obsidian), the rules below state that reading as currently known, and an observed case overrides them:

- **Frontmatter** opens only on the first line of the source, a line holding the fence alone, and closes at the next such line. A fence never closed opens no frontmatter.
- **Fences** follow CommonMark [macfarlane2024]. A fence of at least three backticks or tildes closes at a fence of the same character and at least the same length. An unclosed fence runs to the end of its container.
- **Code spans**: a run of backticks opens a code span, and the next run of the same width closes it [macfarlane2024]. When no such run follows, the first narrower run closes the span, and the excess backticks of the opening run stay literal: in ``` ``foo`bar` ```, one backtick stays literal before the code `foo`. A run closed by neither is literal as a whole.
- **Indented code** opens on a line indented by at least four columns outside a paragraph. An indented line inside a paragraph continues the paragraph.
- **Display mathematics** opens at `$$` and closes at the next `$$`, possibly on a later line. A line inside an open formula opens no block, even when it starts with a block marker. A blank line keeps the formula open. An unclosed `$$` opening a line opens a formula running to the end of its container, as an unclosed fence does. An unclosed `$$` inside a sentence stays literal. Instead, a syntax may let a blank line close the paragraph, and the formula with it, and may leave every unclosed `$$` literal.
- **Inline mathematics** opens at a single `$` followed by a character other than a space, and closes at the next `$` preceded by a character other than a space, on the same line. A `$` preceded by a space closes no mathematics, and the search goes on.
- **Precedence**: constructs open from left to right, and no construct opens inside an opaque region. Therefore, a `$` inside a code span opens no mathematics, and a link inside a code span is code. A bracket inside a code span closes no link text, so `` [a `]` b](c) `` is one link [macfarlane2024]. However, a link prevails over a code span crossing its text, as in `` [a`](b)` ``. Instead, CommonMark gives the precedence to the crossing code span [macfarlane2024]. A syntax may state that precedence.
- **Link text** may hold embeds, such as an image inside a link, and no other link. The alias of a wikilink holds no link.
- **Escapes**: outside the opaque regions, a backslash before an ASCII punctuation character escapes that character [macfarlane2024]. An escaped character delimits nothing: an escaped `$` closes no mathematics, and an escaped parenthesis belongs to a destination. The escaped `|` is the exception: it still separates the alias of a wikilink, and its backslash stays out of the destination, since a wikilink in a table cell escapes its separator.
- **Headings** open with one to six `#`, followed by a space, a tab or the line ending. At most three spaces may precede the marker. The content excludes the optional closing run of `#` and its surrounding spaces, as in CommonMark [macfarlane2024]. Therefore, `#tag` opens no heading.
- **Thematic breaks and setext underlines** end a paragraph and form no region. A line of separated dashes is a thematic break, not a list item.
- **Callouts**: a quotation is a callout when its first line opens with `[!type]`. A `+` or a `-` right after the closing bracket is its fold sign.
- **Links** take the Markdown form `[text](destination "title")` and the wiki forms `[[destination]]` and `[[destination|text]]`. Each form has an embed, opened by `!`. The title of a Markdown link belongs to neither child region, and a wikilink without an alias has no link text. A wikilink runs to its first closing `]]`, so `[[a](b)]]` holds a wikilink to `a](b)`. A syntax may exclude characters from the destination of a wikilink.

## Kinds of the structured sources

Merismos extracts the prose strings of the three other source types. These regions never nest:

| Source type | Kind | Construct | Value | Attributes |
| --- | --- | --- | --- | --- |
| `yaml` | `yaml-value` | a string scalar of any style, without its anchor and its tag | the string, as YAML decodes it | `pointer`: the JSON Pointer of the scalar, or of its mapping for a key; `style`: `plain`, `single-quoted`, `double-quoted`, `literal` or `folded`; `document`: the index of its document |
| `yaml` | `yaml-comment` | a comment | the text after `#`, its leading spaces included | none |
| `python` | `python-docstring` | the string literal documenting a module, a class or a function | the string, dedented as the syntax states | `owner`: `module`, `class` or `function`; `name`: the qualified name of the owner as `__qualname__` writes it, empty for a module |
| `python` | `python-comment` | a comment | the text after `#`, its leading spaces included | none |
| `commit` | `commit-subject` | the subject of the message | the subject after the cleanup of the message | none |
| `commit` | `commit-body` | the paragraphs after the subject, before the scissors line and without the final block of trailers | the paragraphs after the cleanup of the message | none |

The syntax of each type selects the strings to extract, such as the comments left out by a declared pattern, and the cleanup of a commit message. The range of a structured region covers its whole construct:

- a scalar or a string literal with its quotes, its prefix or its indicators;
- a comment with its `#`;
- a subject or a body from the start of its first line to the end of the text of its last line, the comment lines left out of its value included.

Its content is null, and two fields carry the string instead:

- `value` holds the decoded string;
- `pieces` lists triples (offset in the value, offset in the source, length), all counted in code points, each mapping a run of the value to the source run copied verbatim into it.

Decoding produces the code points of the value outside every piece, such as a folded line break or a decoded escape. Each such code point originates from the source text between the two pieces around it. A consumer may segment the value as Markdown. Then, the pieces map each region of the value back to the source. ^pieces

Every decoded value is compared with the value read by the parser of its format. A disagreement raises an error for the whole source, since it reveals a defect of the decoder that a partial result would hide.

## Versioning

The contract carries version 1. Two changes keep the version:

- adding an attribute to a kind;
- correcting a case not yet observed to the reading observed in Obsidian, since the contract follows that reading.

Every other change to the kinds, to the fields or to the expected regions starts version 2. In particular, a new kind starts version 2, since a new opaque kind or a new container changes the regions already returned for other kinds. ^versioning

## Conformance cases

A conformance file names the contract and lists its cases. Each case holds five keys:

- `id`, the name of the case;
- `source`, the source type of the text;
- `observed`, the version of Obsidian used to observe the reading of the case, or null before any observation;
- `text`, the source;
- `regions`, the expected regions, in the order fixed under [nesting and order](#^nesting).

An optional `note` states the point of reading fixed by the case. A file naming another contract is rejected. ^cases

## Sources

- [macfarlane2024] ○ [J. MacFarlane, *CommonMark Spec*, version 0.31.2, 2024](https://spec.commonmark.org/0.31.2/)
