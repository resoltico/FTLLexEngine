formatted-num = { NUMBER($amount, minimumFractionDigits: 2) }
formatted-date = { DATETIME($date, dateStyle: "long") }
chained = { NUMBER(NUMBER($val, minimumFractionDigits: 0), maximumFractionDigits: 2) }
