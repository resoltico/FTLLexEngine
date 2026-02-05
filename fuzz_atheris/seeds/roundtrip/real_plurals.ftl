# Plural rules exercising all CLDR categories
emails =
    { $count ->
        [zero] No emails
        [one] One email
        [two] Two emails
        [few] { $count } emails
        [many] { $count } emails
       *[other] { $count } emails
    }
