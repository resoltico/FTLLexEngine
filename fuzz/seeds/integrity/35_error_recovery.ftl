# 35_error_recovery.ftl - Malformed content that should produce junk entries
valid-msg = This is valid

# Missing closing brace
incomplete-placeable = { $var

# Unclosed string
unclosed-string = "missing quote

# Invalid syntax
invalid-syntax = message = { unknown-function() }

# More valid content after errors
another-valid = This should parse fine