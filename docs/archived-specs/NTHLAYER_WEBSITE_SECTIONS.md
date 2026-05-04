# New Sections for nthlayer.io

## Insertion Points

These two components should be inserted into the existing `index.html` in this order:

1. **DemoCallout** — insert AFTER `<ScenarioAnimation />` and BEFORE the `<div id="layers">` sticky lifecycle bar
2. **IndustryGapSection** — insert AFTER the component deep-dive sections (`COMPONENTS.map(...)`) and BEFORE `<LoopDiagram />`

The components use the exact same design language, fonts, colours, and spacing patterns as the existing site. They use the `useInView` hook already defined in the codebase.

---

## Component 1: DemoCallout

Insert after `<ScenarioAnimation />` and before the sticky lifecycle bar.

```jsx
function DemoCallout() {
  const ref = useRef(null);
  const inView = useInView(ref, 0.2);
  return (
    <section ref={ref} id="demo" style={{
      padding: "80px 24px",
      textAlign: "center",
      opacity: inView ? 1 : 0,
      transform: inView ? "translateY(0)" : "translateY(30px)",
      transition: "all 0.8s cubic-bezier(0.16, 1, 0.3, 1)",
    }}>
      <div style={{
        maxWidth: 700,
        margin: "0 auto",
        padding: "48px 40px",
        background: "rgba(136,192,208,0.03)",
        border: "1px solid rgba(136,192,208,0.08)",
        borderRadius: 16,
      }}>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 11,
          letterSpacing: "0.15em",
          color: "#88c0d0",
          textTransform: "uppercase",
          fontWeight: 600,
          marginBottom: 20,
        }}>
          LIVE DEMO
        </div>
        <h2 style={{
          fontFamily: "'Instrument Serif', Georgia, serif",
          fontSize: 32,
          color: "#F0F0F3",
          fontWeight: 400,
          margin: "0 0 16px 0",
          lineHeight: 1.2,
        }}>
          Watch it work
        </h2>
        <p style={{
          fontFamily: "'Inter', sans-serif",
          fontSize: 15,
          color: "#9CA3AF",
          maxWidth: 520,
          margin: "0 auto 32px auto",
          lineHeight: 1.7,
          fontWeight: 300,
        }}>
          29 services. 4 platforms. Two concurrent incidents — one AI model regression,
          one infrastructure failure. Watch NthLayer detect, separate, and resolve both
          in 90 seconds.
        </p>
        <a href="/demo" style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 13,
          padding: "14px 28px",
          borderRadius: 8,
          background: "rgba(136,192,208,0.1)",
          color: "#88c0d0",
          border: "1px solid rgba(136,192,208,0.3)",
          textDecoration: "none",
          fontWeight: 600,
          cursor: "pointer",
          display: "inline-block",
          transition: "all 0.2s ease",
        }}
          onMouseEnter={e => { e.target.style.background = "rgba(136,192,208,0.15)"; e.target.style.borderColor = "rgba(136,192,208,0.5)"; }}
          onMouseLeave={e => { e.target.style.background = "rgba(136,192,208,0.1)"; e.target.style.borderColor = "rgba(136,192,208,0.3)"; }}
        >
          Launch demo →
        </a>
      </div>
    </section>
  );
}
```

---

## Component 2: IndustryGapSection

Insert after the component deep-dive sections and before `<LoopDiagram />`.

This section presents 6 external reference points from the research, each showing a named source, what they said, and the gap it reveals. The cumulative effect is what matters: independent voices all describing the same missing piece.

```jsx
const GAP_EVIDENCE = [
  {
    source: "Brendan Burns",
    role: "Kubernetes co-founder, Corporate VP Azure",
    context: "SREcon25 Americas, 2025",
    insight: "There is rarely a clean 'working' or 'broken' signal from AI releases. We monitor latency and errors, but that no longer says your system is working right.",
    gap: "Traditional metrics confirmed insufficient by the architect of modern infrastructure.",
    color: "#81a1c1",
  },
  {
    source: "LangChain State of AI Agents",
    role: "1,300+ respondents, December 2025",
    context: "Industry survey",
    insight: "89% of organisations have implemented observability for their AI agents. Yet 32% still cite quality as the number one production barrier.",
    gap: "The industry has observability. It just measures the wrong things.",
    color: "#5e81ac",
  },
  {
    source: "Alex Palcuie",
    role: "AI Reliability Engineering, Anthropic",
    context: "QCon London, March 2026",
    insight: "Every time I asked Claude what happened, it would say 'request volume increase, this is a capacity problem.' The real issue was a broken cache. Claude will get wrong correlation versus causation.",
    gap: "Even frontier AI labs cannot trust their own models' judgment during incidents.",
    color: "#b48ead",
  },
  {
    source: "Charity Majors",
    role: "Co-founder & CTO, Honeycomb",
    context: "Co-author, Observability Engineering (O'Reilly)",
    insight: "You can't understand a model in a vacuum. With the surge of generative AI, complexity was increasing fast. It's now been cranked up even faster. The wheels are coming off.",
    gap: "The person who wrote the book on observability says the current model is breaking.",
    color: "#ebcb8b",
  },
  {
    source: "Gartner",
    role: "Daryl Plummer, Distinguished VP Analyst",
    context: "Gartner IT Symposium",
    insight: "The implementation of guardrails, security filters, human oversight, or even security observability are not sufficient to ensure consistently appropriate agent use.",
    gap: "The enterprise's most trusted analyst declares the entire current stack insufficient.",
    color: "#bf616a",
  },
  {
    source: "Dynatrace Pulse of Agentic AI",
    role: "919 senior technology leaders, January 2026",
    context: "Global survey",
    insight: "42% report limited real-time visibility to trace agent behaviour. 69% of agentic AI decisions are currently human-verified. Only 13% use fully autonomous agents.",
    gap: "The majority of AI decisions require human verification. Nobody is measuring the override rate as an SLO.",
    color: "#a3be8c",
  },
];

function IndustryGapSection() {
  const ref = useRef(null);
  const inView = useInView(ref, 0.1);

  return (
    <section ref={ref} style={{
      padding: "100px 24px 80px",
      maxWidth: 900,
      margin: "0 auto",
    }}>
      {/* Section header */}
      <div style={{
        textAlign: "center",
        marginBottom: 60,
        opacity: inView ? 1 : 0,
        transform: inView ? "translateY(0)" : "translateY(30px)",
        transition: "all 0.8s cubic-bezier(0.16, 1, 0.3, 1)",
      }}>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 11,
          letterSpacing: "0.15em",
          color: "#88c0d0",
          textTransform: "uppercase",
          fontWeight: 600,
          marginBottom: 20,
        }}>
          THE GAP
        </div>
        <h2 style={{
          fontFamily: "'Instrument Serif', Georgia, serif",
          fontSize: 36,
          color: "#F0F0F3",
          fontWeight: 400,
          margin: "0 0 16px 0",
          lineHeight: 1.2,
        }}>
          The industry is describing a problem<br />
          <span style={{
            background: "linear-gradient(135deg, #5e81ac, #88c0d0, #8fbcbb)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}>nobody is filling</span>
        </h2>
        <p style={{
          fontFamily: "'Inter', sans-serif",
          fontSize: 15,
          color: "#9CA3AF",
          maxWidth: 560,
          margin: "0 auto",
          lineHeight: 1.7,
          fontWeight: 300,
        }}>
          Every major voice in observability, reliability, and AI operations is converging
          on the same conclusion: traditional monitoring cannot tell you whether an AI agent
          is making good decisions. Here's what they're saying.
        </p>
      </div>

      {/* Evidence cards */}
      <div style={{
        display: "flex",
        flexDirection: "column",
        gap: 16,
      }}>
        {GAP_EVIDENCE.map((item, i) => (
          <div key={i} style={{
            display: "flex",
            gap: 20,
            padding: "24px 28px",
            background: "rgba(11,17,32,0.5)",
            border: "1px solid #1E2A3A",
            borderLeft: `3px solid ${item.color}`,
            borderRadius: "0 10px 10px 0",
            opacity: inView ? 1 : 0,
            transform: inView ? "translateY(0)" : "translateY(20px)",
            transition: `all 0.6s cubic-bezier(0.16, 1, 0.3, 1) ${0.1 + i * 0.08}s`,
          }}>
            {/* Left: source info */}
            <div style={{ minWidth: 160, flexShrink: 0 }}>
              <div style={{
                fontFamily: "'Inter', sans-serif",
                fontSize: 14,
                color: "#F0F0F3",
                fontWeight: 600,
                marginBottom: 4,
              }}>
                {item.source}
              </div>
              <div style={{
                fontFamily: "'Inter', sans-serif",
                fontSize: 11,
                color: "#6B7F99",
                lineHeight: 1.4,
                marginBottom: 4,
              }}>
                {item.role}
              </div>
              <div style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 10,
                color: "#4A5568",
              }}>
                {item.context}
              </div>
            </div>

            {/* Right: insight + gap */}
            <div style={{ flex: 1 }}>
              <p style={{
                fontFamily: "'Inter', sans-serif",
                fontSize: 13,
                color: "#9CA3AF",
                lineHeight: 1.65,
                margin: "0 0 10px 0",
                fontStyle: "italic",
              }}>
                "{item.insight}"
              </p>
              <p style={{
                fontFamily: "'Inter', sans-serif",
                fontSize: 12,
                color: item.color,
                margin: 0,
                fontWeight: 500,
              }}>
                → {item.gap}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* NthLayer answer */}
      <div style={{
        marginTop: 48,
        textAlign: "center",
        opacity: inView ? 1 : 0,
        transform: inView ? "translateY(0)" : "translateY(20px)",
        transition: "all 0.8s cubic-bezier(0.16, 1, 0.3, 1) 0.6s",
      }}>
        <div style={{
          maxWidth: 640,
          margin: "0 auto",
          padding: "32px 36px",
          background: "rgba(136,192,208,0.04)",
          border: "1px solid rgba(136,192,208,0.12)",
          borderRadius: 12,
        }}>
          <p style={{
            fontFamily: "'Instrument Serif', Georgia, serif",
            fontSize: 22,
            color: "#F0F0F3",
            fontWeight: 400,
            margin: "0 0 12px 0",
            lineHeight: 1.3,
          }}>
            NthLayer fills the gap.
          </p>
          <p style={{
            fontFamily: "'Inter', sans-serif",
            fontSize: 14,
            color: "#9CA3AF",
            margin: "0 0 6px 0",
            lineHeight: 1.7,
            fontWeight: 300,
          }}>
            Judgment quality as a first-class SLO. Spec-driven correlation across declared
            dependencies. A closed loop from incident back to contract.
          </p>
          <p style={{
            fontFamily: "'Inter', sans-serif",
            fontSize: 14,
            color: "#9CA3AF",
            margin: 0,
            lineHeight: 1.7,
            fontWeight: 300,
          }}>
            Not inside the agent. Outside it. Because enforcement outside the system
            is governance. Instructions inside the system are hope.
          </p>
        </div>

        {/* Read the full analysis link */}
        <a href="/research" style={{
          display: "inline-block",
          marginTop: 24,
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 12,
          color: "#6B7F99",
          textDecoration: "none",
          letterSpacing: "0.05em",
          transition: "color 0.2s ease",
        }}
          onMouseEnter={e => e.target.style.color = "#88c0d0"}
          onMouseLeave={e => e.target.style.color = "#6B7F99"}
        >
          Read the full analysis →
        </a>
      </div>
    </section>
  );
}
```

---

## Insertion Reference

In the existing JSX render, the structure should become:

```jsx
      {/* Animated scenario */}
      <ScenarioAnimation />

      {/* NEW: Demo callout */}
      <DemoCallout />

      {/* Sticky lifecycle bar */}
      <div id="layers" style={{...}}>
        <LifecycleBar activeIndex={activeIdx} />
      </div>

      {/* Component sections */}
      {COMPONENTS.map((comp, i) => (
        <ComponentSection ... />
      ))}

      {/* NEW: Industry gap evidence */}
      <IndustryGapSection />

      {/* Closed loop */}
      <LoopDiagram />

      {/* CTA */}
      <CTASection />
```

---

## Design Notes for Claude Code

**Fonts used (already loaded on the site):**
- `'Instrument Serif', Georgia, serif` — headings
- `'Inter', sans-serif` — body text
- `'JetBrains Mono', monospace` — labels, code, CTAs

**Colour palette (already defined on the site):**
- Background: `#0B1120`
- Primary accent: `#88c0d0` (frost teal)
- Text primary: `#F0F0F3`
- Text secondary: `#9CA3AF`
- Text muted: `#4A5568`, `#6B7F99`
- Border: `#1E2A3A`
- Component colours: `#81a1c1` (spec), `#5e81ac` (generate), `#b48ead` (measure), `#ebcb8b` (correlate), `#bf616a` (respond), `#a3be8c` (learn)

**The evidence cards use the component colours as left borders.** Each source is colour-coded to the NthLayer component that addresses the gap it describes:
- Burns (infrastructure) → `#81a1c1` (spec — declares what reliable means)
- LangChain (wrong metrics) → `#5e81ac` (generate — creates the right monitoring)
- Palcuie (correlation) → `#b48ead` (measure — judgment quality)
- Majors (complexity) → `#ebcb8b` (correlate — system-level view)
- Gartner (insufficient) → `#bf616a` (respond — active remediation)
- Dynatrace (human verification) → `#a3be8c` (learn — closed loop from overrides)

**The `useInView` hook is already defined in the codebase.** Both components use it for scroll-triggered fade-in animations matching the existing site's behaviour.

**Responsive:** On mobile (< 640px), the evidence cards should stack the source info above the insight text rather than side-by-side. Add a media query or use a flex-wrap approach. The existing site handles this at the CSS level, so follow the same pattern.

**The demo link points to `/demo`** which should serve the `nthlayer-topology.html` file. This can be a simple static file serve or a redirect, depending on hosting setup.

**The research link points to `/research`** which will serve the full research report (Asset 2). If that page doesn't exist yet, the link can be temporarily hidden or pointed to the GitHub repo.
