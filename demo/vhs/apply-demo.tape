# NthLayer Apply Demo - Hero GIF
# Shows the core value prop: "20 hours of SRE work in 5 minutes"
# Run from repo root: vhs demo/vhs/apply-demo.tape

Output demo/vhs/nthlayer-apply.gif

Set Shell "bash"
Set FontFamily "Menlo"
Set FontSize 14
Set Width 900
Set Height 600
Set Theme "Dracula"
Set Padding 20
Set Framerate 30

# Force color output for Rich
Env FORCE_COLOR "1"

# Show what we're doing
Type "# Generate reliability stack from service spec"
Enter
Sleep 1s

# Run nthlayer apply
Type ".venv/bin/nthlayer apply examples/services/checkout-service.yaml"
Enter
Sleep 3s

# Show generated files
Type "ls generated/checkout-service/"
Enter
Sleep 3s
