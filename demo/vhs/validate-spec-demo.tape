# NthLayer validate-spec Demo - Policy Validation GIF
# Shows OPA/conftest policy validation
# Run from repo root: vhs demo/vhs/validate-spec-demo.tape

Output demo/vhs/validate-spec-demo.gif

Set Shell "bash"
Set FontFamily "Menlo"
Set FontSize 14
Set Width 900
Set Height 550
Set Theme "Dracula"
Set Padding 20
Set Framerate 30

# Force color output for Rich
Env FORCE_COLOR "1"

# Show what we're doing
Type "# Validate service spec against policies"
Enter
Sleep 1s

# Run the validate-spec command
Type ".venv/bin/nthlayer validate-spec examples/services/checkout-service.yaml --verbose"
Enter
Sleep 4s

Sleep 2s
