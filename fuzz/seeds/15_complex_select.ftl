complex = { $gender ->
    [male] { $count ->
        [one] He has one item
       *[other] He has { $count } items
    }
    [female] { $count ->
        [one] She has one item
       *[other] She has { $count } items
    }
   *[other] { $count ->
        [one] They have one item
       *[other] They have { $count } items
    }
}
