# NthLayer SLO Demo
# Shows SLO inspection commands
# Run from repo root: vhs demo/vhs/slo-demo.tape

Output demo/vhs/slo-demo.gif

Set Shell "bash"
Set FontSize 16
Set Width 900
Set Height 600
Set Theme "Dracula"
Set Padding 20
Set Framerate 30

# Show SLO list (using local venv)
Type ".venv/bin/nthlayer slo list --dir examples/services"
Enter
Sleep 2500ms

# Show SLO details for a specific service
Type ".venv/bin/nthlayer slo show examples/services/checkout-service.yaml"
Enter
Sleep 2500ms

Sleep 2s
