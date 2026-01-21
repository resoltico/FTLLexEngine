# BiDi Isolating Mark stress tests (FSI, PDI, LRI, RLI)
# These are U+2066, U+2067, U+2068, U+2069
bidi-explicit = { "\u2066" } { $name } { "\u2069" }
bidi-rtl = { "\u2067" } { $name } { "\u2069" }
bidi-nested = { "\u2068" } One { "\u2068" } Two { "\u2069" } { "\u2069" }

# Real-world mixed directionality
arabic-name = { $title } { "\u2068" } { $name } { "\u2069" } تم الحفظ
long-bidi = { "\u2068" } LTR { "\u2067" } RTL { "\u2066" } FSI { "\u2069" } { "\u2069" } { "\u2069" }
