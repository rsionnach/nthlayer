# NthLayer SLO Demo
# Shows SLO inspection commands
# Run from repo root: vhs demo/vhs/slo-demo.tape

Output demo/vhs/slo-demo.gif

Set Shell "bash"
Set FontFamily "Menlo"
Set FontSize 16
Set Width 900
Set Height 600
Set Theme "Dracula"
Set Padding 20
Set Framerate 30

# Force color output for Rich
Env FORCE_COLOR "1"

# Show SLO details for a specific service
Type ".venv/bin/nthlayer slo show checkout-service --file examples/services/checkout-service.yaml"
Enter
Sleep 4s

Sleep 2s
