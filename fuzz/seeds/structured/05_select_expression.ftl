emails = { $count ->
    [one] You have one email
   *[other] You have { $count } emails
}

gender-msg = { $gender ->
    [masculine] He went
    [feminine] She went
   *[other] They went
}
