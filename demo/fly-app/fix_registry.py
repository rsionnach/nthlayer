import re

# Read file
with open('app.py', 'r') as f:
    content = f.read()

# Replace all Counter, Gauge, Histogram declarations to add registry=registry
# Match patterns like: Counter('name', 'desc', ['labels'])
# Replace with: Counter('name', 'desc', ['labels'], registry=registry)

patterns = [
    (r"(Counter\([^)]+\))", r"\1"),
    (r"(Gauge\([^)]+\))", r"\1"),
    (r"(Histogram\([^)]+\))", r"\1"),
]

# Add registry=registry before the closing parenthesis if not already present
content = re.sub(
    r"(Counter|Gauge|Histogram)\(([^)]+)\)(?!\s*,\s*registry=)",
    r"\1(\2, registry=registry)",
    content
)

# Fix double registry=registry
content = content.replace(', registry=registry, registry=registry', ', registry=registry')

with open('app.py', 'w') as f:
    f.write(content)

print("Fixed registry references")
