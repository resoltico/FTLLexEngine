# Combining multiple FTL features into complex structures

-brand = Brand
    .name = Fluent
    .version = 1.0

# Term reference in default variant of a nested select inside an attribute
complex-msg = Value
    .description = { $platform ->
        [web] Visit { -brand.name } Online
        [mobile] { $os ->
            [ios] App Store { -brand.version }
           *[other] Play Store { -brand.name }
        }
       *[other] Desktop { -brand.name }
    }

# Function calls with complex arguments mixed with references
system-log = { DATETIME($date) }: { -brand.name } status is { $code ->
    [404] { $verbose ->
        [true] Page not found at { $url }
       *[false] Missing
    }
   *[other] Code { NUMBER($code) }
}
