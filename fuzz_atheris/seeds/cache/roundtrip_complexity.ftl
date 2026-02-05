# Seed for Roundtrip Fuzzer: Nested Placeable and Brace Complexity
# Tests the serializer's Ability to handle literal braces vs expressions.

msg01 = Value with { "{" } literal brace and { $variable } reference.
msg02 = Nested { { $var } } placeables.
msg03 = Double nested { { { "triply nested" } } } literal.
msg04 = Multi-line
    { $count ->
        [one] One
       *[other] { $count } items with { "{" } braces { "}" }
    }
msg05 =
    .attr = Attribute with { "{" }
    .nested = { { $ref } }
