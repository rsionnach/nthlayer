# NthLayer Portfolio Demo
# Shows cross-vendor SLO aggregation across all services
# Run from repo root: vhs demo/vhs/portfolio-demo.tape

Output demo/vhs/portfolio-demo.gif

Set Shell "bash"
Set FontSize 16
Set Width 900
Set Height 600
Set Theme "Dracula"
Set Padding 20
Set Framerate 30

# Run portfolio command on examples (using local venv)
Type ".venv/bin/nthlayer portfolio --dir examples/services"
Enter
Sleep 3s

Sleep 2s
