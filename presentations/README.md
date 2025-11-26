# NthLayer Presentations

**Presentation-as-code with Slidev**

All NthLayer presentation decks, version-controlled and maintainable.

---

## 🚀 Quick Start

```bash
# Install dependencies
npm install

# Run overview deck in dev mode
cd decks/01-overview
npm run dev

# Export to PDF
npm run export -- --output ../../exports/nthlayer-overview.pdf
```

---

## 📚 Available Decks

### 1. Overview (Main Pitch)
**File:** `decks/01-overview/slides.md`
**Duration:** 10-15 minutes
**Audience:** General, conferences, first-time viewers

**Key messages:**
- NthLayer is standalone (no service catalog required)
- Creates SLOs automatically
- Git + YAML workflow
- ResLayer is production-ready

### 2. Technical Deep Dive
**File:** `decks/02-technical-deep-dive/slides.md`
**Duration:** 25-30 minutes
**Audience:** Engineering teams, technical decision-makers

**Key messages:**
- Layer architecture pattern
- SLO creation engine
- Provider registry design
- Database schema

### 3. Sales Demo
**File:** `decks/03-demo-walkthrough/slides.md`
**Duration:** 20-25 minutes
**Audience:** Sales demos, customer onboarding

**Key messages:**
- Problem: Manual ops glue
- Solution: Operationalization
- Live workflow demo
- Flexibility (standalone vs catalog)

### 4. Investor Pitch
**File:** `decks/04-investor-pitch/slides.md`
**Duration:** 10 minutes
**Audience:** Investors, accelerators, pitch competitions

**Key messages:**
- Market opportunity ($15B DevOps tools)
- Operationalization gap
- ResLayer validation
- Platform approach

---

## 🎨 Project Structure

```
presentations/
├── package.json              # Dependencies
├── README.md                 # This file
├── components/               # Reusable Vue components
│   └── (shared components)
├── styles/                   # Shared themes/styles
│   └── nthlayer-theme.css
├── demos/                    # Python demo files
│   ├── slo-creation.py
│   ├── standalone-workflow.py
│   └── budget-calculation.py
├── decks/                    # Individual presentations
│   ├── 01-overview/
│   │   ├── slides.md
│   │   └── assets/
│   ├── 02-technical-deep-dive/
│   ├── 03-demo-walkthrough/
│   └── 04-investor-pitch/
└── exports/                  # Exported PDFs/PPTXs
    └── (generated files)
```

---

## 🔧 Development Workflow

### Creating New Slide
```markdown
---
layout: center
---

# Your Slide Title

Content goes here

- Bullet points
- More content
```

### Adding Python Demo
```markdown
\`\`\`python {monaco-run}
# Your Python code here
print("Hello, NthLayer!")
\`\`\`
```

### Adding Mermaid Diagram
```markdown
\`\`\`mermaid
graph LR
    A[Input] --> B[NthLayer]
    B --> C[Output]
\`\`\`
```

---

## 📤 Exporting Presentations

### Export to PDF
```bash
cd decks/01-overview
npm run export -- --output ../../exports/overview.pdf
```

### Export to PPTX
```bash
npm run export --format pptx -- --output ../../exports/overview.pptx
```

### Build Static Site
```bash
npm run build
# Outputs to dist/
```

---

## 🎯 Key Messaging (All Decks)

### Always Emphasize:
✅ **Standalone by default** - No service catalog required
✅ **Creates SLOs** - Not just tracks them
✅ **Git + YAML workflow** - Simple and flexible
✅ **Catalog optional** - Integrate with Backstage/Cortex if you want
✅ **Production-ready** - ResLayer works today

### Visual Priority:
1. Show YAML file first (standalone)
2. Show what NthLayer creates
3. Then mention catalog integration as optional

---

## 🐍 Python Demos

All demos emphasize:
- SLO creation (not just tracking)
- Standalone operation
- No external dependencies needed
- Complete workflow in code

See `demos/` folder for reusable examples.

---

## 🎨 Theme & Branding

### Colors (NthLayer Brand)
```css
--nthlayer-primary: #2563eb    /* Blue */
--nthlayer-secondary: #7c3aed  /* Purple */
--nthlayer-success: #10b981    /* Green */
--nthlayer-warning: #f59e0b    /* Amber */
--nthlayer-error: #ef4444      /* Red */
```

### Typography
- Headings: Bold, large
- Code: `Fira Code` or `Monaco`
- Body: `Inter` or system default

---

## 📝 Contributing

### Adding a New Deck
1. Create folder: `decks/05-new-deck/`
2. Create `slides.md`
3. Add to this README
4. Test with `npm run dev`

### Updating Shared Components
1. Edit files in `components/`
2. Test across all decks
3. Update documentation

---

## 🚀 Next Steps

1. **Install:** `npm install`
2. **Run:** `cd decks/01-overview && npm run dev`
3. **Edit:** Modify `slides.md` and see live reload
4. **Export:** `npm run export` when ready

---

**Happy presenting!** 🎤
