rating = { $stars ->
    [1] Poor
    [2] Fair
    [3] Good
    [4] Great
   *[5] Excellent
}

price-range = { $tier ->
    [-1] Below range
    [0] Free
    [99.99] Premium
   *[other] Standard
}
