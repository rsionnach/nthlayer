# Logo Setup - Complete ✅

Your NthLayer logo has been added to the presentations!

## What Was Done

### Logo File
- **Location:** `presentations/public/nthlayer_dark_logo.png`
- **Size:** 1.0MB
- **Format:** PNG

### Presentation Updates
- **File:** `presentations/decks/01-overview/slides.md`
- **Changes:**
  1. Added `logoHeader: '/nthlayer_dark_logo.png'` to frontmatter
  2. Added logo to title slide (centered, larger display)

## Where Logo Appears

### 1. Header (All Slides)
The logo appears in the **top-right corner** of every slide via `logoHeader` config.

### 2. Title Slide
The logo appears **centered and larger** on the opening slide for prominent branding.

## View Your Presentation

```bash
cd presentations
npm run dev
```

Then open: http://localhost:3030

## Adjust Logo Size

### Header Logo
The header logo size is controlled by the theme. If you need to adjust it, you can override in custom CSS.

### Title Slide Logo
To change the title slide logo size, edit the `class="h-24"` value:

```markdown
<img src="/nthlayer_dark_logo.png" class="h-20" />  # Smaller
<img src="/nthlayer_dark_logo.png" class="h-32" />  # Larger
```

## Use Logo in Other Slides

To add the logo to any slide:

```markdown
# Your Slide Title

<div class="flex justify-center">
  <img src="/nthlayer_dark_logo.png" class="h-16" />
</div>

Your content here...
```

## File Paths

Slidev looks for files in:
- `presentations/public/` - Recommended for assets
- Accessed via `/filename.png` in markdown

## Tips

✅ Use SVG for best scaling quality  
✅ Use PNG with transparent background for dark themes  
✅ Keep file size reasonable (<2MB)  
✅ Test on both light and dark backgrounds  

---

**Setup Date:** December 26, 2024  
**Status:** ✅ Complete  
**Logo Active:** Yes
