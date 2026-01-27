# 36_function_chaining.ftl - Function calls within other function calls
nested-number = { NUMBER(NUMBER($value, minimumFractionDigits: 0), minimumFractionDigits: 2) }
datetime-in-number = { NUMBER(DATETIME($date, month: "numeric")) }