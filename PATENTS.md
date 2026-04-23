---
afad: "3.5"
version: "0.164.0"
domain: LEGAL
updated: "2026-04-22"
route:
  keywords: [patents, legal, license, fluent, apache, mit, babel]
  questions: ["what is the patent position?", "does the project include a patent grant?", "what about the Fluent specification license?"]
---

# Patent Notes

**Purpose**: Summarize the patent posture of FTLLexEngine and its main upstream legal inputs.
**Prerequisites**: None.

## Overview

FTLLexEngine is distributed under the MIT License. MIT does not contain an explicit patent grant or patent retaliation clause, so this repository does not add one on top of the license text shipped in `LICENSE`.

The project’s legal posture is shaped by two notable upstream inputs plus this repository’s own license choice:

| Component | License | Explicit Patent Grant |
|:----------|:--------|:----------------------|
| FTLLexEngine | MIT | No explicit patent clause |
| Fluent specification materials | Apache-2.0 | Yes |
| Babel (optional dependency) | BSD-3-Clause | No explicit patent clause |

## Fluent Specification

Project Fluent specification materials are published under Apache License 2.0, which includes an explicit contributor patent license in Section 3. That grant applies to the specification materials and upstream contributions to them; it does not convert this repository into an Apache-licensed implementation.

## Contributor Guidance

Contributors should only submit code they are authorized to license under this repository’s terms. If you know code or data is encumbered by patent restrictions that would conflict with normal project use, do not contribute it here.

## Disclaimer

This file is informational and not legal advice. For legal interpretation or patent risk analysis, consult qualified counsel.
