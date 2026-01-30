# Diverse Unicode stress testing
# Arabic (RTL)
arabic-msg = { $name } مبروك
# Zalgo / Combining marks
stale-text = H̡͌ḛ̢͑l̩̖ͦl̰̜ͩo̪͉ͮ W̪͉o̪͉r̪͉l̪͉d̪͉
# Emoji and Symbols
emoji-power = 🚀 Infinity & Beyond ✨ 
# Zero-width characters & Whitespace
invisible-man = Message​with​zero​width​spaces
# Control characters (escaped for visibility in source, but we should use literals in seed)
# We will use the structured fuzzer's logic to generate these, but a literal seed helps.
control-chars = Special {"\u0000"} {"\u001F"} {"\u007F"}
# Mathematical / Greek
math-msg = Σ x_i = { $sum }
# BIDI Isolating marks (Unicode 0.8.0 feature)
bidi-text = Starting { "\u2068" } { $inner } { "\u2069" } ending
