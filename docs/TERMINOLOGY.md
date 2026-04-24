---
afad: "4.0"
version: "0.165.0"
domain: TERMINOLOGY
updated: "2026-04-24"
route:
  keywords: [terminology, glossary, message, term, resource, locale code, strict mode]
  questions: ["what does resource mean here?", "what is the difference between a message and a term?", "what does strict mode mean in FTLLexEngine?"]
---

# Terminology

**Purpose**: Keep the project’s documentation and code comments aligned on a small set of terms.
**Prerequisites**: None.

## Core Terms

| Term | Meaning |
|:-----|:--------|
| Message | Public FTL entry such as `welcome = Hello` |
| Term | Private reusable FTL entry such as `-brand = FTLLexEngine` |
| FTL source | Raw `.ftl` text before parsing |
| FTL resource | Parsed `Resource` AST |
| Resource loader | Object that returns FTL source for a locale/resource id pair |
| Locale code | Canonical locale identifier used by the runtime |
| Strict mode | Fail-fast behavior that raises integrity exceptions instead of returning soft fallbacks |
| Boot validation | Startup path that proves resource cleanliness and schema correctness before traffic |
| Parser-only install | `pip install ftllexengine`; syntax, AST, validation, and zero-dependency helper surfaces without Babel |
| Full runtime install | `pip install ftllexengine[babel]`; bundle/localization formatting, locale parsing, and Babel-backed helper surfaces |

## Resource Disambiguation

“Resource” can mean different things in localization systems. In this repository, prefer explicit phrases:

- Say `FTL source` for raw text.
- Say `Resource` or `FTL resource` for the parsed AST.
- Say `resource loader` for the object that loads source material.

## Naming Style

- Use `Fluent` when referring to the Fluent specification or runtime concepts.
- Use `FTL` when referring to the language syntax or `.ftl` files.
- Prefer `parser-only install` and `full runtime install` over ad-hoc phrases like “without Babel” or “with Babel” when describing supported install modes.
- Use readable input examples such as `en_US`, `de_DE`, and `lv_LV`; reserve lowercase forms like `en_us` for normalized internal/cache-key examples.
