# NthLayer drift Demo - Reliability Drift Detection GIF
# Shows drift analysis detecting gradual budget decline
# Run from repo root: vhs demo/vhs/drift-demo.tape

Output demo/vhs/drift-demo.gif

Set Shell "bash"
Set FontFamily "Menlo"
Set FontSize 14
Set Width 900
Set Height 750
Set Theme "Dracula"
Set Padding 20
Set Framerate 20

# Force color output for Rich
Env FORCE_COLOR "1"

# Show what we're doing
Type "# Analyze reliability drift trends"
Enter
Sleep 2s

# Run the drift command with demo mode
Type ".venv/bin/nthlayer drift examples/services/payment-api.yaml --demo"
Sleep 500ms
Enter
Sleep 7s

# Hold on the final result
Sleep 10s
