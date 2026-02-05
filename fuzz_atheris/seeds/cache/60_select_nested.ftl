msg = { $type ->
    [cat] { $count ->
        [one] One cat
       *[other] { $count } cats
    }
   *[other] Animal
}
