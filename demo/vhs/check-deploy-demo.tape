# NthLayer check-deploy Demo - Deployment Gates GIF
# Shows a deployment being BLOCKED due to exhausted error budget
# Run from repo root: vhs demo/vhs/check-deploy-demo.tape

Output demo/vhs/check-deploy-demo.gif

Set Shell "bash"
Set FontFamily "Menlo"
Set FontSize 14
Set Width 900
Set Height 700
Set Theme "Dracula"
Set Padding 20
Set Framerate 20

# Force color output for Rich
Env FORCE_COLOR "1"

# Show what we're doing
Type "# Check error budget before deploying"
Enter
Sleep 2s

# Run the check-deploy command with blocked demo mode
Type ".venv/bin/nthlayer check-deploy examples/services/checkout-service.yaml --demo-blocked"
Sleep 500ms
Enter
Sleep 6s

# Hold on the final result
Sleep 4s
