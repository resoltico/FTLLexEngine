# Seed for Unicode Fuzzer: Focus on Normalization in Values
# Identifiers remain ASCII (required), but values can contain Unicode.

norm_nfc = Value with ñ (NFC)
norm_nfd = Value with ñ (NFD)
compound = Value with 👨‍👩‍👧‍👦 (ZWJ Emoji)
rtl_text = Text with RTL marker: \u200F
surrogates = Tricky pair: \uD83D\uDCA9
