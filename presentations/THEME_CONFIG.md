# Neversink Theme Configuration

## Current Configuration

The presentation uses the **Neversink** theme with the following settings:

```yaml
themeConfig:
  color: dark              # Dark background mode
  primary: blue           # Primary color scheme (blue)
  accent: purple          # Accent color scheme (purple) 
  code-theme: github-dark # Code syntax highlighting theme
```

## Color Schemes Available

### Dark Background Colors
- **dark** - Dark gray/black background
- **black** - Pure black background
- **navy** - Navy blue background
- **navy-light** - Lighter navy background

### Primary/Accent Colors
Choose from these color schemes for `primary` and `accent`:

**Vibrant Colors:**
- `blue` - Professional blue (currently primary)
- `purple` - Rich purple (currently accent)
- `indigo` - Deep indigo
- `violet` - Bright violet
- `cyan` - Bright cyan
- `teal` - Teal/turquoise
- `green` - Vibrant green
- `emerald` - Emerald green

**Warm Colors:**
- `red` - Bold red
- `orange` - Vibrant orange
- `amber` - Amber/gold
- `yellow` - Bright yellow
- `lime` - Lime green

**Other:**
- `pink` - Hot pink
- `rose` - Rose pink
- `fuchsia` - Fuchsia/magenta
- `sky` - Sky blue

### Code Themes
- `github-dark` - GitHub's dark theme (current)
- `github-light` - GitHub's light theme
- `dracula` - Dracula theme
- `nord` - Nord theme
- `monokai` - Monokai theme

## How Text Colors Work

With `color: dark`, the theme automatically sets:
- **Background:** Dark color (near black)
- **Text:** Bright/white for high contrast
- **Code blocks:** Syntax highlighted with bright colors
- **Headings:** Uses primary color (blue)
- **Accents:** Uses accent color (purple)
- **Links/highlights:** Bright versions of primary/accent

## Customizing

To change colors, edit `slides.md` frontmatter:

```yaml
themeConfig:
  color: dark              # Keep dark background
  primary: cyan           # Change to cyan primary
  accent: green           # Change to green accent
  code-theme: dracula     # Change code theme
```

## CSS Variables

The theme sets these CSS variables automatically:

```css
--neversink-bg-color          /* Background color */
--neversink-text-color        /* Main text color (bright on dark) */
--neversink-fg-color          /* Foreground elements */
--neversink-border-color      /* Borders */
--neversink-highlight-color   /* Highlights */
--neversink-bg-code-color     /* Code block background */
--neversink-fg-code-color     /* Code block text */
```

## Current Color Palette

With `color: dark`, `primary: blue`, `accent: purple`:

- **Background:** Dark gray/black (#0f172a)
- **Text:** White/near-white (#f8fafc)
- **Primary (blue):** #3b82f6
- **Accent (purple):** #a855f7
- **Code background:** Darker gray
- **Code text:** Bright with syntax colors

## Tips for Readability

1. ✅ Keep `color: dark` for dark background
2. ✅ Use bright `primary` colors (blue, cyan, green, purple)
3. ✅ Use contrasting `accent` colors
4. ✅ Use dark code themes (`github-dark`, `dracula`, `nord`)
5. ✅ Text automatically becomes bright/white on dark backgrounds

## Examples

### Tech/Professional
```yaml
themeConfig:
  color: dark
  primary: blue      # Professional
  accent: cyan       # Tech vibe
  code-theme: github-dark
```

### Creative/Bold
```yaml
themeConfig:
  color: dark
  primary: fuchsia   # Bold
  accent: yellow     # High contrast
  code-theme: dracula
```

### Natural/Calm
```yaml
themeConfig:
  color: dark
  primary: teal      # Calm
  accent: emerald    # Natural
  code-theme: nord
```

### Current (NthLayer Branding)
```yaml
themeConfig:
  color: dark
  primary: blue      # Matches NthLayer blue
  accent: purple     # Matches NthLayer purple
  code-theme: github-dark
```

---

**Last Updated:** Based on Neversink theme documentation
**Theme Version:** 0.4.0+
**More Info:** https://gureckis.github.io/slidev-theme-neversink/colors
