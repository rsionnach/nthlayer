# NthLayer Plan Demo
# Shows preview of what would be generated
# Run from repo root: vhs demo/vhs/plan-demo.tape

Output demo/vhs/plan-demo.gif

Set Shell "bash"
Set FontFamily "Menlo"
Set FontSize 16
Set Width 900
Set Height 550
Set Theme "Dracula"
Set Padding 20
Set Framerate 30

# Force color output for Rich
Env FORCE_COLOR "1"

# Run plan command
Type ".venv/bin/nthlayer plan examples/services/checkout-service.yaml"
Enter
Sleep 4s

Sleep 2s
