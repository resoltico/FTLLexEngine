<!--
RETRIEVAL_HINTS:
  keywords: [terminology, definitions, glossary, fluent terms, message, term, pattern, placeable, resource]
  answers: [what is a message, what is a term, what is a pattern, fluent terminology]
  related: [../README.md, DOC_02_Types.md]
-->
# FTLLexEngine Terminology Guide

**Official terminology reference for FTLLexEngine project**

This document establishes the standard terminology used throughout FTLLexEngine's codebase, documentation, and communication. Consistent terminology improves clarity and reduces confusion.

---

## Core Terminology

### Fluent System Terms

| Term | Definition | Usage Example |
|------|------------|---------------|
| **Fluent** | The localization system and specification | "Fluent supports asymmetric localization" |
| **FTL** | The file format (Fluent Translation List) | "Save translations in .ftl files" |
| **.ftl files** | Files using the FTL format | "Load main.ftl and errors.ftl" |
| **Fluent syntax** | The language syntax used in .ftl files | "Learn Fluent syntax at projectfluent.org" |
| **FTL specification** | The formal grammar and rules (v1.0) | "Implements FTL specification v1.0" |

**Rationale**: "Fluent" is the system, "FTL" is the file format, "Fluent syntax" is the language.

---

### Message Structure Terms

| Term | Definition | Code Example | Prose Example |
|------|------------|--------------|---------------|
| **Message** | A translatable unit with an ID | `Message` class | "The welcome message" |
| **Message ID** | The identifier for a message | `message_id` (snake_case) | "message ID" (two words) |
| **Message identifier** | Formal variant of message ID | `message_id: str` | "message identifier" |
| **Term** | Reusable translation (prefixed with `-`) | `Term` class | "The -brand term" |
| **Term ID** | The identifier for a term | `term_id` (snake_case) | "term ID" |
| **Pattern** | The text content of a message/term | `Pattern` class | "The message pattern" |
| **Placeable** | An expression wrapped in `{ }` braces | `Placeable` class | "A variable placeable" |
| **Attribute** | Named sub-value of a message | `Attribute` class | "The tooltip attribute" |

**Naming Conventions**:
- **Code**: Use snake_case (`message_id`, `term_id`)
- **Prose**: Use two words ("message ID", "term ID")
- **Classes**: Use PascalCase (`Message`, `Term`, `Pattern`)

---

## CRITICAL: "Resource" Disambiguation

**WARNING**: The term "resource" has **three distinct meanings** in FTLLexEngine. **ALWAYS specify which meaning** when using this term.

### The Three Meanings of "Resource"

#### 1. FTL Resource (AST)

**What it is**: The parsed Abstract Syntax Tree (AST) root node returned by `parse_ftl()`.

**Type**: `Resource` class from `ftllexengine.syntax.ast`

**Usage Context**: AST manipulation, linting, transformation, serialization

**How to Reference**:
- ✅ **"the Resource AST node"**
- ✅ **"the parsed Resource"**
- ✅ **"Resource object"**
- ✅ **"AST Resource"**
- ❌ ~~"resource"~~ (ambiguous)

**Code Example**:
```python
from ftllexengine import parse_ftl
from ftllexengine.syntax.ast import Resource

# Correct: Clear context
resource_ast: Resource = parse_ftl(ftl_source)  # Resource AST node
for entry in resource_ast.entries:
    print(entry)

# Ambiguous: What type of resource?
resource = parse_ftl(ftl_source)  # Is this AST, source, or loader?
```

**Prose Example**:
```markdown
✅ "The Resource AST node contains all parsed entries"
✅ "parse_ftl() returns a Resource object representing the AST"
❌ "The resource contains all entries" (which resource?)
```

---

#### 2. FTL Source (String)

**What it is**: The string content containing FTL syntax, passed to `add_resource(source: str)`.

**Type**: `str` (or `FTLSource` type alias)

**Usage Context**: Loading translations at runtime, validation, file I/O

**How to Reference**:
- ✅ **"FTL source"**
- ✅ **"FTL source text"**
- ✅ **"FTL source code"**
- ✅ **"ftl_source"** (variable name)
- ❌ ~~"resource"~~ (ambiguous)

**Code Example**:
```python
from ftllexengine import FluentBundle
from ftllexengine.localization import FTLSource

# Correct: Clear naming
ftl_source: FTLSource = """
hello = Hello, World!
"""
bundle.add_resource(ftl_source)  # String parameter

# Ambiguous: What type of resource?
resource = "hello = Hello!"  # Is this a source string or AST?
bundle.add_resource(resource)
```

**Prose Example**:
```markdown
✅ "Pass FTL source to add_resource()"
✅ "The FTL source text is validated before loading"
❌ "Pass the resource to add_resource()" (which resource?)
```

---

#### 3. Resource Loader

**What it is**: System for loading .ftl files from disk/network.

**Types**: `PathResourceLoader` (file system), `ResourceLoader` (protocol)

**Usage Context**: Multi-locale applications with file-based translations

**How to Reference**:
- ✅ **"resource loader"**
- ✅ **"PathResourceLoader instance"**
- ✅ **"ResourceLoader protocol"**
- ✅ **"loader"** (variable name)
- ❌ ~~"resource"~~ (ambiguous)

**Code Example**:
```python
from ftllexengine.localization import PathResourceLoader, ResourceLoader

# Correct: Clear naming
loader: ResourceLoader = PathResourceLoader("locales/{locale}")
ftl_source = loader.load("en", "main.ftl")

# Ambiguous: What type of resource?
resource = PathResourceLoader("locales/{locale}")  # This is a LOADER
```

**Prose Example**:
```markdown
✅ "PathResourceLoader loads .ftl files from disk"
✅ "Implement the ResourceLoader protocol for custom loaders"
❌ "The resource loads .ftl files" (resource doesn't load files, loaders do!)
```

---

### Disambiguation Decision Tree

When writing documentation or code, ask:

```
Am I talking about...

├─ An AST object from parse_ftl()?
│  └─ Use: "Resource AST", "Resource object", variable: resource_ast
│
├─ A string containing FTL syntax?
│  └─ Use: "FTL source", "FTL source text", variable: ftl_source
│
└─ A system that loads .ftl files?
   └─ Use: "resource loader", "PathResourceLoader", variable: loader
```

---

### Variable Naming Conventions

**Recommended variable names** to avoid ambiguity:

```python
# FTL Resource (AST)
resource_ast = parse_ftl(ftl_source)
ast_root = parse_ftl(ftl_source)
parsed_resource = parse_ftl(ftl_source)

# FTL Source (String)
ftl_source = "hello = World"
ftl_content = Path("main.ftl").read_text()
source_text = "..."

# Resource Loader
loader = PathResourceLoader("locales/{locale}")
resource_loader = PathResourceLoader("locales/{locale}")
disk_loader = PathResourceLoader("locales/{locale}")
```

**Avoid**:
```python
# ❌ Ambiguous - which type of resource?
resource = ...
res = ...
r = ...
```

---

### Method Naming Context

Some methods use "resource" in their name - context determines meaning:

| Method | "Resource" Meaning | Full Type |
|--------|-------------------|-----------|
| `add_resource(source)` | **FTL source (string)** | Parameter is `str` |
| `validate_resource(source)` | **FTL source (string)** | Parameter is `str` |
| `parse_ftl(source)` returns | **Resource AST** | Returns `Resource` object |
| `PathResourceLoader(...)` | **Resource loader** | Creates loader instance |
| `ResourceLoader.load(...)` | **FTL source (string)** | Returns `str` |

**Note**: `add_resource()` and `validate_resource()` take **FTL source** (string), NOT Resource AST objects.

---

## Other Important Terms

### Locale Terms

| Term | Definition | Examples |
|------|------------|----------|
| **Locale** | Language and regional variant | "en_US", "lv_LV", "ar_SA" |
| **Locale code** | String identifier for locale | `locale: str`, `LocaleCode` type alias |
| **Language code** | Two-letter ISO 639-1 code | "en", "lv", "ar" |
| **Territory code** | Two-letter ISO 3166-1 code | "US", "LV", "SA" |
| **CLDR** | Common Locale Data Repository | "CLDR plural rules" |

**Formatting**: Use underscore (`en_US`) or hyphen (`en-US`) - both supported.

---

### Error Handling Terms

| Term | Definition | Usage |
|------|------------|-------|
| **Errors tuple** | Immutable tuple of FluentError instances | `errors: tuple[FluentError, ...]` |
| **Fallback** | Default value when error occurs | "Returns readable fallback" |
| **Graceful degradation** | Continues with fallback instead of crashing | "Never raises, always degrades gracefully" |
| **Junk entry** | Unparseable FTL syntax | `Junk` AST node type |

---

### AST Terms

| Term | Definition | Type |
|------|------------|------|
| **AST** | Abstract Syntax Tree | `Resource` root with entries |
| **Entry** | Top-level AST node | `Message`, `Term`, `Comment`, `Junk` |
| **Expression** | Evaluable AST node | `VariableReference`, `FunctionReference`, etc. |
| **Selector** | Select expression condition | Part of `SelectExpression` |
| **Variant** | Select expression branch | `Variant` with key and value |

---

### Function Terms

| Term | Definition | Examples |
|------|------------|----------|
| **Built-in function** | Provided by FTLLexEngine | NUMBER, DATETIME |
| **Custom function** | User-defined function | CURRENCY, PHONE |
| **Function name** | UPPERCASE identifier | "NUMBER", "CURRENCY" |
| **Function parameter** | Named argument to function | minimumFractionDigits, currencyCode |
| **camelCase** | FTL parameter convention | minimumFractionDigits |
| **snake_case** | Python parameter convention | minimum_fraction_digits |

---

## Writing Guidelines

### Documentation Style

1. **Be explicit about "resource" meaning**:
   ```markdown
   ❌ "Load the resource into the bundle"
   ✅ "Load the FTL source into the bundle"
   ✅ "Parse the Resource AST using parse_ftl()"
   ✅ "Use the resource loader to fetch .ftl files"
   ```

2. **Use consistent capitalization**:
   ```markdown
   ✅ "Fluent" (system), "FTL" (format), "Fluent syntax" (language)
   ❌ "fluent", "ftl", "FTL syntax"
   ```

3. **Prose vs Code formatting**:
   ```markdown
   ✅ "The message ID 'welcome' is used in `bundle.format_pattern()`"
   ❌ "The `message ID` welcome is used in bundle.format_pattern()"
   ```

### Code Style

1. **Variable names should indicate type**:
   ```python
   # Good
   ftl_source = "hello = World"
   resource_ast = parse_ftl(ftl_source)
   loader = PathResourceLoader("...")

   # Avoid
   resource = "hello = World"  # Which type?
   r = parse_ftl(ftl_source)  # Unclear
   ```

2. **Type annotations clarify intent**:
   ```python
   from ftllexengine.syntax.ast import Resource
   from ftllexengine.localization import FTLSource, ResourceLoader

   def process_ftl(ftl_source: FTLSource) -> Resource:
       resource_ast: Resource = parse_ftl(ftl_source)
       return resource_ast

   def load_translations(loader: ResourceLoader, locale: str) -> FTLSource:
       ftl_source: FTLSource = loader.load(locale, "main.ftl")
       return ftl_source
   ```

---

## Terminology Checklist

When reviewing documentation or code, verify:

- [ ] "Resource" is always qualified (AST, source, or loader)
- [ ] Message ID uses correct case (prose: "message ID", code: `message_id`)
- [ ] "Fluent" refers to system, "FTL" refers to file format
- [ ] Variable names indicate their type (`ftl_source` vs `resource_ast`)
- [ ] Capitalization is consistent ("Fluent", not "fluent")
- [ ] Parameter names use correct case (FTL: camelCase, Python: snake_case)

---

## Common Pitfalls

### ❌ Pitfall 1: Ambiguous "resource"

```markdown
❌ "The bundle loads resources from disk"
✅ "The bundle loads FTL source from resource loaders on disk"
```

### ❌ Pitfall 2: Mixing "Fluent" and "FTL"

```markdown
❌ "FTL is a localization system for .ftl files"
✅ "Fluent is a localization system using .ftl files (FTL format)"
```

### ❌ Pitfall 3: Inconsistent capitalization

```python
# ❌ Inconsistent
from ftllexengine import fluentBundle  # Wrong
from ftllexengine import FLUENTBUNDLE  # Wrong

# ✅ Correct
from ftllexengine import FluentBundle
```

---

## Quick Reference

**When in doubt**:

| Context | Use This Term |
|---------|---------------|
| AST object from parse_ftl() | "Resource AST", `resource_ast` |
| String with FTL syntax | "FTL source", `ftl_source` |
| File loader system | "resource loader", `loader` |
| The Fluent system | "Fluent" |
| File format (.ftl) | "FTL" or ".ftl files" |
| The syntax language | "Fluent syntax" |
| Translatable unit | "message" |
| Message identifier | "message ID" (prose), `message_id` (code) |

---

## Glossary

Complete alphabetical reference:

| Term | Short Definition | Full Details |
|------|------------------|--------------|
| **AST** | Abstract Syntax Tree | Parsed representation of FTL source |
| **Attribute** | Named sub-value of message | `.tooltip`, `.aria-label` |
| **Bundle** | Single-locale message collection | `FluentBundle` class |
| **CLDR** | Common Locale Data Repository | Unicode locale data standard |
| **Entry** | Top-level AST node | Message, Term, Comment, or Junk |
| **Expression** | Evaluable AST component | Variables, functions, selects |
| **Fallback** | Default when error occurs | Readable placeholder value |
| **Fluent** | The localization system | Overall specification and ecosystem |
| **Fluent syntax** | The language syntax | Grammar rules for .ftl files |
| **FTL** | Fluent Translation List file format | .ftl file extension |
| **FTL source** | String containing FTL syntax | What you pass to `add_resource()` |
| **Function** | Formatting function | NUMBER, DATETIME, custom |
| **Junk** | Unparseable FTL syntax | Parser error recovery node |
| **Locale** | Language and region | "en_US", "lv_LV" |
| **Localization** | Multi-locale orchestration | `FluentLocalization` class |
| **Message** | Translatable unit with ID | `Message` AST node |
| **Message ID** | Message identifier | Key used in `format_pattern()` |
| **Pattern** | Text content of message | `Pattern` AST node |
| **Placeable** | Expression in `{ }` braces | `Placeable` AST node |
| **Resource (AST)** | Parsed FTL structure | `Resource` object from `parse_ftl()` |
| **Resource loader** | System loading .ftl files | `PathResourceLoader`, custom loaders |
| **Selector** | Select expression condition | Plural category, gender, etc. |
| **Term** | Reusable translation | Prefixed with `-` |
| **Variant** | Select expression branch | Key-value pair in select |

---

**Terminology Guide Last Updated**: December 26, 2025
**FTLLexEngine Version**: 0.33.0

**See Also**:
- [README.md - Terminology Section](README.md#terminology)
- [docs/DOC_00_Index.md](docs/DOC_00_Index.md) - Complete API reference
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
