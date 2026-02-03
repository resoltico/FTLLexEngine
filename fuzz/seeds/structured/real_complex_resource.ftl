### Application Menu

-brand-name = FTLEngine
-platform =
    { $os ->
        [windows] Windows
        [macos] macOS
       *[other] Linux
    }

# Welcome message with brand reference
welcome = Welcome to { -brand-name } on { -platform }!
    .title = { -brand-name } Dashboard
    .aria-label = Main welcome banner for { -brand-name }

## User Section

# Notification count with NUMBER formatting
notifications =
    { NUMBER($count) ->
        [zero] No new notifications
        [one] One new notification
       *[other] { NUMBER($count) } new notifications
    }
    .badge = { NUMBER($count) }

file-size = { NUMBER($bytes, maximumFractionDigits: 2) } MB
price = { CURRENCY($amount, currency: "USD") }
updated = Last updated: { DATETIME($date, dateStyle: "long") }

# Cross-references
summary = { welcome } You have { notifications }.
