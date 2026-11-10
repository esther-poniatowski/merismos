---
tags:
  - guide
index: "[Merismos documentation](docs/_index.md)"
aliases:
  - Merismos guide
---
# Using Merismos

A consumer of Merismos segments its sources and selects the kinds read by its policy. Every finding of the consumer then maps back to an exact offset. This guide assumes an environment holding Merismos, as [the contribution guidelines](../CONTRIBUTING.md) install it.

## Segmenting a source

To segment one source, a consumer passes the text and its source type. The result lists the regions in the order of the [span kinds](span-kinds.md#^nesting), and `select` rejects a kind unknown to the source type, so that a misspelled kind fails instead of selecting nothing:

```python
from merismos import segment

segmentation = segment("Let $x_i$ and `y` vary.", "markdown")
for region in segmentation.select(["inline-math"]):
    print(segmentation.text(region.content))  # x_i
```

To segment under another grammar, the consumer passes its own [syntax file](syntax-files.md):

```python
from pathlib import Path

segmentation = segment(text, "markdown", syntax=Path("config/markdown-syntax.yml"))
```

The function `segment` keeps one segmenter per packaged syntax, and reads a syntax file of the consumer again at each call, so that an edit of the file takes effect. A consumer segmenting many sources under its own syntax builds one segmenter and reuses it:

```python
from merismos import default_registry

segmenter = default_registry().segmenter("markdown", Path("config/markdown-syntax.yml"))
segmentations = [segmenter.segment(text) for text in texts]
```

## Reading and masking regions

Two operations apply a policy with exact offsets, without any knowledge of the policy itself:

- `mask(source, regions, fill)` replaces the ranges of regions by a fill character and keeps every line break, so that the offsets and line numbers of the masked text stay those of the source;
- `content_view(source, region)` returns the content of a region without its gaps, such as the quotation markers inside a formula of a callout, and maps each position back to the source.

The following call masks the code and the mathematics of a note before a prose check:

```python
from merismos import mask

masked = mask(text, segmentation.select(["inline-code", "fenced-code", "inline-math", "display-math"]))
```

A region of a structured source carries a decoded string instead of a content. Its method `to_source` maps an offset of the value, such as the position of a finding, to the source:

```python
for region in segment(yaml_text, "yaml").select(["yaml-value"]):
    if region.attributes["pointer"].endswith("/gloss"):
        offset = region.string.to_source(0)
```

## Scanning the paragraphs of another parser

A consumer keeping a block parser of its own passes the spans of the lines of one paragraph, without their container prefixes, and receives the inline regions of the paragraph with source offsets. The text between two consecutive spans, after the line ending, becomes a gap of each construct crossing it:

```python
from merismos import Span, inline_regions

paragraph = inline_regions("> a $$x\n> y$$\n", [Span(2, 7), Span(10, 14)])
```

## Adding a source type

A consumer segmenting a type absent from Merismos registers a builder of its own. The builder receives the syntax document and the name of the type, and returns an object with a method `segment(source)`:

```python
from pathlib import Path

from merismos import SourceType, default_registry

registry = default_registry()
registry.register(SourceType("latex", build_latex_segmenter), default_syntax=Path("config/latex.yml"))
segmenter = registry.segmenter("latex")
```

## Command line

The command `merismos segment` prints the regions of a file as JSON, one region per line, for inspection or for a consumer written in another language:

```console
merismos segment notes/a.md --type markdown --kind inline-math
```

The command `merismos conform` checks a syntax against a conformance file, and exits with status 1 when a case returns other regions than expected. A consumer passing its own syntax checks it against the published cases:

```console
merismos conform specs/conformance/markdown.yml --syntax config/markdown-syntax.yml
```

Each mismatch is reported as the first differing region of its case, and the last line gives the number of conforming cases.

## Observing cases in Obsidian

Merismos follows the reading of Obsidian, and a case becomes binding once it is observed there. The command `merismos observe` writes an observation vault: one note per Markdown case, holding exactly the text of the case, and a checklist stating the expected reading of each case:

```console
merismos observe specs/conformance/markdown.yml --output-dir .agent-work/obsidian-observation
```

A second run replaces the notes, which derive from the cases. It stops with exit status 2 when the folder already holds a checklist, since the checklist may hold ticked cases; the option `--force` replaces it.

The folder `.agent-work/` lies under the root of the repository, and Git ignores it. Unlike a system temporary directory, the folder is reachable from the folder dialog of Obsidian and survives a restart.

The observation then takes four steps:

1. Open the folder as a vault in Obsidian, then open the note `_checklist.md`.
2. Open each case from its link, in the reading view, and compare the rendering with the regions listed under the case: each formula, code span, heading, quotation, callout and link, with the text of its content.
3. Tick a case when Obsidian renders every listed region and no other one; note the difference otherwise.
4. Write the version of Obsidian, shown under Settings › General, in the field `observed` of each ticked case of the conformance file, and correct or report each case whose reading differs.

A correction of an unobserved case keeps the version of the contract, as the [versioning rule](span-kinds.md#^versioning) states.
