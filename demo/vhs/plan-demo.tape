# NthLayer Plan Demo
# Shows preview of what would be generated
# Run from repo root: vhs demo/vhs/plan-demo.tape

Output demo/vhs/plan-demo.gif

Set Shell "bash"
Set FontSize 16
Set Width 900
Set Height 550
Set Theme "Dracula"
Set Padding 20
Set Framerate 30

# Run plan command (using local venv)
Type ".venv/bin/nthlayer plan examples/services/checkout-service.yaml"
Enter
Sleep 2500ms

Sleep 2s
