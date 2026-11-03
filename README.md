# merismos

![Maintenance](https://img.shields.io/maintenance/yes/2026)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.12-blue)](https://www.python.org/)
[![License: GPL](https://img.shields.io/badge/License-GPL--3.0-yellow.svg)](https://opensource.org/licenses/GPL-3.0)

Segments documents into typed regions with exact offsets, for the tools that check texts.

---

## Overview

Before checking a text, a tool must locate the constructs of the text, such as its code, its mathematics and its links. Merismos segments a Markdown source into typed regions, such as inline mathematics or the destination of a link. Merismos also extracts the prose strings of structured sources, such as YAML files and Python docstrings. Each region carries its exact offsets in the source, and nested regions keep their containment. Then, each consumer applies its own policy to the regions: Hermeneia masks the mathematics, whereas Onomasia scans its symbols.

### Motivation

Three tools currently detect the regions of a Markdown document on their own: Hermeneia, Anagraphe, and the glossary checker of Geonexus that becomes Onomasia. Two limitations follow:

- each tool detects inline mathematics with its own regular expression, and the three expressions disagree on edge cases, so the checks of one note read different formulas;
- correcting one detector repairs one tool only.

Merismos removes both limitations, since one library defines the regions for every consumer. Its grammar lives in syntax files, so a consumer changes a dialect without code. Its conformance cases fix the reading of the edge cases met so far, each to be confirmed in Obsidian.

### Status

Pre-alpha. The package segments the four shipped source types. Its [conformance cases for Markdown](specs/conformance/markdown.yml) await their observation in Obsidian. The [segmentation decision](docs/adr/segmentation-contract.md) is accepted.

---

## Quick Start

The following call segments a note and prints the content of its inline mathematics:

```python
from merismos import segment

segmentation = segment("Let $x_i$ vary.", "markdown")
print([segmentation.text(region.content) for region in segmentation.select(["inline-math"])])
```

The [guide](docs/guide.md) covers masking, decoded strings, syntax files and the command line.

---

## Documentation

The [documentation index](docs/_index.md) is the entry point.

---

## Contributing

Contributions follow the [contribution guidelines](CONTRIBUTING.md).

---

## License

This project is licensed under the terms of the [GNU General Public License v3.0](LICENSE).
