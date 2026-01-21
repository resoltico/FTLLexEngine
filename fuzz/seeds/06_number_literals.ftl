rating = { $stars ->
    [0] No stars
    [1] One star
    [2] Two stars
    [3] Three stars
    [4] Four stars
   *[5] Five stars
}

price-range = { $price ->
    [0.0] Free
    [0.99] Budget
    [9.99] Standard
   *[99.99] Premium
}

# Proper Number Literals
direct-int = { 123 }
direct-float = { 12.34 }
direct-neg = { -0.5 }
