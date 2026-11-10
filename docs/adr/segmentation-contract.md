---
tags:
  - decision
status: accepted
created: 2026-11-02
revised: 2026-11-03
index: "[Architecture decisions](docs/adr/_index.md)"
aliases:
  - Segmentation contract decision
---
# Segmentation contract

> [!QUESTION] Goal: in which form does Merismos return the regions of a source, how does a consumer change the grammar, and when does the contract change?

The [decision on designation and typography](https://github.com/esther-poniatowski/geonexus/blob/main/docs/_decisions/designation-and-typography.md) of Geonexus creates Merismos, and settles six points for it:

- the three consumers: Onomasia, Hermeneia and Anagraphe;
- the regions to recognize in Markdown, and the extraction of the prose strings of YAML, Python and commit sources;
- conformance cases following the reading of Obsidian;
- the policy applied to the regions by each consumer, never by Merismos;
- the parser of blocks, kept by Hermeneia beside the inline regions of Merismos;
- the grammar of link destinations, kept by Anagraphe.

Merismos consumes no contract, so the graph of contracts places it first. The present record decides the form of the regions, the configuration of the grammar, and the changes that start a new version of the contract. The [specification of the span kinds](../span-kinds.md) states the result normatively.

## Decision

**A grammar declared in syntax files.** The delimiters, markers and limits of each construct, the constructs enabled, and the strings extracted are values of a [syntax file](../syntax-files.md). The algorithms of the segmenters stay fixed. Merismos ships one syntax per source type, and a consumer passes its own file to change a dialect. ^syntax-files

**Kinds selected by the consumer.** Merismos reads no configuration of the consumer. The consumer passes the type of each source, and selects in its own configuration the kinds to read among those of the type. ^source-types

**A registry as the extension point.** A source type maps to the builder of its segmenter in a registry. A consumer registers a type absent from Merismos without changing the library. ^registry

**A scanner of its own.** The Markdown segmenter scans blocks with a stack of containers, then scans each paragraph and heading for inline constructs. ^scanner

**Display mathematics above the blocks.** A line inside an open display formula opens no block, so the scanner of blocks asks the scanner of inline constructs whether a paragraph leaves a formula open. ^display-math

**Offsets in code points**, as the [offset rule](../span-kinds.md#^offsets) states them. ^offsets

**A sorted forest of regions**, in the [order of the specification](../span-kinds.md#^nesting). ^forest

**A range, a content and gaps** for each region, the gaps standing for the [container prefixes](../span-kinds.md#^gaps) interrupting its content. ^content-and-gaps

**Decoded strings verified against their parser.** A prose string of a structured source comes with its decoded value and its [pieces](../span-kinds.md#^pieces). A decoder records the origin of each decoded code point, and the pieces are the runs copied verbatim. The decoded value must equal the value read by PyYAML or by Python. ^pieces

**Indented code as a kind.** Indented code joins the kinds listed by the designation decision, since a `$` inside it would otherwise open mathematics. ^indented-code

**Cases that record their observation.** Each conformance case names the version of Obsidian used to observe its reading. The [versioning rule](../span-kinds.md#^versioning) states when an unobserved case may still change. ^observation

**A new kind as a new version**, as the [versioning rule](../span-kinds.md#^versioning) states it. ^new-kinds

## Constraints that decide the form

- **Dialects differ in their delimiters, not in their algorithms.** A vault writing mathematics between other delimiters, or without wikilinks, reads the same constructs under other values.
- **The three consumers are written in Python.** Python indexes a string by code points, so an offset in code points slices the source directly in each consumer.
- **Consumers apply opposite policies to one region.** Hermeneia masks a whole formula, delimiters included, whereas Onomasia reads the symbols between the delimiters. Therefore, a region must locate both its construct and its content.
- **A container interrupts the content of a region.** A formula inside a callout continues on lines opening with `>`. A consumer reading the symbols must skip those markers, while a consumer reporting a finding must keep the offsets of the source.
- **markdown-it-py locates no inline construct.** Its tokens locate a block by its lines, and an inline construct by no offset, so gaps and inline offsets would be recomputed around it. The Python parsers available to the consumers share this limit.
- **A finding is reported at a line and a column of its file.** Therefore, a finding inside a decoded YAML string must map back to the source, through every escape and folded line.
- **Obsidian documents its syntax by examples, not by a grammar.** An edge case is settled by observing Obsidian. Therefore, a case written before any observation may prove wrong.
- **A new kind can change the regions of the other kinds.** A new opaque kind removes the regions opening inside its construct, and a new container adds gaps to the regions nested in it.

## Options weighed

**Configuration of the grammar.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| A grammar fixed in code | No file format to maintain | Every dialect needs a change of the library |
| Options passed by each call | No file | Every consumer restates the grammar in its own code, and two consumers drift apart |
| **A syntax file per dialect** | One declarative source per dialect, shared by consumers and checked by the conformance command | Taken |

**Basis of the Markdown segmenter.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| markdown-it-py, with an inline layer of its own | A tested parser of blocks, already used by Hermeneia | Its inline tokens carry no offset and its block tokens only line maps, so offsets and gaps would be recomputed around it |
| **A scanner of its own** | Exact offsets and gaps by construction, and no parser dependency | Taken, at the cost of more code to test |

**Unit of the offsets.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| UTF-8 bytes | Matches the file on disk | Each consumer converts every offset before slicing a Python string |
| UTF-16 code units | Matches the editors written in TypeScript, Obsidian among them | No consumer is written in TypeScript. This unit would win if a TypeScript tool, such as Ekphrasis, consumed the regions |
| Lines and columns | Readable in a report | A column needs a unit anyway, and a consumer converts each pair before slicing the source |
| **Code points** | Slices the source directly in every consumer | Taken |

**Structure of the regions.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| One list per kind | A consumer reads one kind without filtering | The lists drop containment, so a consumer cannot tell a formula inside a heading from a formula in a paragraph |
| **A sorted forest** | One list keeps containment and serves every kind | Taken |

**Extent of a region.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| The range only | One pair of offsets | A consumer reading the content parses the delimiters again |
| The content only | Holds the text read by a scanning consumer | A masking consumer cannot reach the delimiters |
| The range and the content, without gaps | Serves both policies | A formula inside a callout hands its quotation markers to the scanner as TeX |
| **The range, the content and the gaps** | Each policy finds its part of the region without parsing | Taken |

**Prose strings of structured sources.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| The range of the token only | Merismos stays free of decoders | Each consumer decodes YAML scalars and Python literals itself, so the decoders stay duplicated across the consumers |
| The decoded value only | Simple to consume | A finding inside the value cannot be located in the source |
| **The value with its pieces** | Decoded once, and every offset maps back | Taken |

**Trust in the decoders.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| Decoded values trusted as computed | No second parse | A decoder diverging from its format on an edge case returns wrong offsets silently |
| Pieces dropped when the values disagree | A consumer never fails | The consumer cannot tell an exact map from a missing one |
| A marker of failure on the region, the other regions kept | One bad string spares the rest of its source | Hides a defect of the decoder behind a partial result, and every check of a consumer must then handle the missing strings |
| **Values compared with their parser, a disagreement raising an error** | A wrong offset never reaches a consumer | Taken. A disagreement is a defect of Merismos, to be repaired. The review of 2026-11-02 found two such defects: anchors and tags, and carriage returns. After their repair, the corpus tested shows no disagreement: 341 YAML files, 1,551 Python modules and 300 commit messages |

**Status of a conformance case.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| Every case normative, observed or not | One rule for every case | A case written from the documentation would bind the consumers to an unverified reading |
| Cases outside the contract until observed | The contract holds only observed readings | The consumers test against no case before the first observation |
| **Every case normative, recording its observation** | Consumers test now, and an unobserved case can be corrected | Taken |

**Effect of a new kind on the version.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| Every new kind within the version | Consumers adopt a new kind without changing their pin | A new opaque kind or a new container changes the regions already returned for other kinds |
| A new version only for opaque kinds and containers | Fewer versions | Any new kind also changes the expected regions of the cases holding its construct |
| **A new version for every new kind** | A consumer pinned to one version receives the same regions | Taken |

## Open points

- The conformance cases of the YAML, Python and commit sources, beside the tests of their decoders.
- Observing the cases left open by the observation of Obsidian 1.15.0, each marked by a null `observed` in the conformance file.
- Mathematics written between two different delimiters, such as `\(` and `\)`. The syntax declares one inline delimiter, and that delimiter both opens and closes the formula.

Seven constructs are not yet kinds, and each awaits a decision:

- setext headings;
- reference links;
- autolinks;
- footnotes;
- tables;
- HTML blocks;
- the comments of Obsidian (`%%`).
