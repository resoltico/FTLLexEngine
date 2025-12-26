-brand = Firefox
    .gender = masculine
    .starts-with-vowel = no

brand-nominative = { -brand }
brand-genitive = { -brand.gender ->
    [masculine] of { -brand }
   *[other] of { -brand }
}
