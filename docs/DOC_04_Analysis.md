---
afad: "4.0"
version: "0.165.0"
domain: ANALYSIS
updated: "2026-04-24"
route:
  keywords: [analysis, detect_cycles, entry_dependency_set, make_cycle_key, dependency graph, cycle key]
  questions: ["where are the dependency-graph helpers documented?", "how do I detect cycles in an FTL dependency graph?", "how do I build namespace-prefixed dependency sets?"]
---

# Analysis Reference

Availability note:
- Parser-only safe: all `ftllexengine.analysis` exports are available without Babel.
- Public module surface: `detect_cycles()`, `entry_dependency_set()`, and `make_cycle_key()`.

---

## `detect_cycles`

Function that finds cyclic paths in a dependency graph.

### Signature
```python
def detect_cycles(dependencies: dict[str, set[str]]) -> list[list[str]]:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `dependencies` | Y | Adjacency mapping keyed by node id |

### Constraints
- Return: List of cycle paths, each closed by repeating the start node at the end
- State: Pure
- Thread: Safe
- Bounds: Honors the module-level cycle-count and DFS-stack limits used by the analysis facade
- Compatibility: Public parser-only helper exposed from `ftllexengine.analysis`

---

## `entry_dependency_set`

Function that builds the canonical mixed message/term dependency set.

### Signature
```python
def entry_dependency_set(
    message_refs: frozenset[str],
    term_refs: frozenset[str],
) -> frozenset[str]:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `message_refs` | Y | Unprefixed referenced message ids |
| `term_refs` | Y | Unprefixed referenced term ids |

### Constraints
- Return: Immutable dependency set using `msg:` and `term:` namespace prefixes
- State: Pure
- Thread: Safe
- Purpose: Canonical public helper for callers that need the same dependency encoding used by runtime and validation internals
- Compatibility: Public parser-only helper exposed from `ftllexengine.analysis`

---

## `make_cycle_key`

Function that converts a cycle path into its canonical display key.

### Signature
```python
def make_cycle_key(cycle: list[str] | tuple[str, ...]) -> str:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `cycle` | Y | Closed cycle path to canonicalize |

### Constraints
- Return: Stable arrow-joined key such as `"msg:a -> term:b -> msg:a"`
- State: Pure
- Thread: Safe
- Purpose: Normalizes equivalent cycle rotations to the same display string
- Compatibility: Public parser-only helper exposed from `ftllexengine.analysis`
