# NthLayer Portfolio Demo
# Shows cross-vendor SLO aggregation across all services
# Run from repo root: vhs demo/vhs/portfolio-demo.tape

Output demo/vhs/portfolio-demo.gif

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

# Run portfolio command on examples
Type ".venv/bin/nthlayer portfolio --path examples/services"
Enter
Sleep 4s

Sleep 2s
