# Nested select with term reference
-gender =
    { $userGender ->
        [male] masculine
        [female] feminine
       *[other] neutral
    }

shared-photos =
    { $userName } { NUMBER($photoCount) ->
        [one] added a new photo
       *[other] added { NUMBER($photoCount) } new photos
    } to { $userGender ->
        [male] his
        [female] her
       *[other] their
    } stream.
