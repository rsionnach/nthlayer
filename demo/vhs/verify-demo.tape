# NthLayer verify Demo - Contract Verification GIF
# Shows metric contract verification before deploy
# Run from repo root: vhs demo/vhs/verify-demo.tape

Output demo/vhs/verify-demo.gif

Set Shell "bash"
Set FontFamily "Menlo"
Set FontSize 14
Set Width 900
Set Height 650
Set Theme "Dracula"
Set Padding 20
Set Framerate 30

# Force color output for Rich
Env FORCE_COLOR "1"

# Show what we're doing
Type "# Verify declared metrics exist in Prometheus"
Enter
Sleep 1s

# Run the verify command with demo mode
Type ".venv/bin/nthlayer verify examples/services/checkout-service.yaml --demo"
Enter
Sleep 4s

Sleep 2s
