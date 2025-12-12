# NthLayer check-deploy Demo - Deployment Gates GIF
# Shows the deployment gate feature with error budget checking
# Run from repo root: vhs demo/vhs/check-deploy-demo.tape

Output demo/vhs/check-deploy-demo.gif

Set Shell "bash"
Set FontFamily "Menlo"
Set FontSize 14
Set Width 900
Set Height 700
Set Theme "Dracula"
Set Padding 20
Set Framerate 30

# Force color output for Rich
Env FORCE_COLOR "1"

# Show what we're doing
Type "# Check error budget before deploying"
Enter
Sleep 1s

# Run the check-deploy command with demo mode
Type ".venv/bin/nthlayer check-deploy examples/services/checkout-service.yaml --demo"
Enter
Sleep 4s

Sleep 2s
