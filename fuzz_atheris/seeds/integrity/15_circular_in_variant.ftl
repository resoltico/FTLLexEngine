msg_a = { $count ->
    [one] { msg_b }
   *[other] Many
}
msg_b = { msg_a }
