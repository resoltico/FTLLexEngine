# Cyclic reference for resolver stress
cyclic-a = { cyclic-b }
cyclic-b = { cyclic-a }

# Deep reference chain
chain-1 = { chain-2 }
chain-2 = { chain-3 }
chain-3 = { chain-4 }
chain-4 = { chain-5 }
chain-5 = Final value
