nested = { { $var } }
double-nested = { { { $deep } } }
mixed-nested = Before { { $middle } } after

# Deeper nesting to exercise parser stack handling
deeply-nested = { { { { { $level5 } } } } }
very-deep = { { { { { { { { { { $level10 } } } } } } } } } }

# Mixed deep nesting with text
deep-mixed = Start { { { { { $deep } } } } } end
