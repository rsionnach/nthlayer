# NthLayer Apply Demo - Hero GIF
# Shows the core value prop: "20 hours of SRE work in 5 minutes"

Output nthlayer-apply.gif

Require nthlayer

Set Shell "bash"
Set FontSize 15
Set Width 800
Set Height 500
Set Theme "Dracula"
Set Padding 20
Set Framerate 30

# Show the service spec
Type "cat service.yaml"
Enter
Sleep 2s

# Run nthlayer apply
Type "nthlayer apply service.yaml"
Enter
Sleep 2s

# Show generated files
Type "ls generated/payment-api/"
Enter
Sleep 2s
