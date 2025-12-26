emails = { $count ->
    [one] You have one email
   *[other] You have { $count } emails
}

gender-message = { $gender ->
    [male] He is online
    [female] She is online
   *[other] They are online
}
