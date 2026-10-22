# TokenTrace redesign — quick reference (copy this)

**Paste into the other window. The agent should follow `DESIGN.md` in the repo root.**

---

## One-sentence brief

> Rebuild TokenTrace as a warm paper ledger: Instrument Serif for the wordmark and hero total, Instrument Sans for UI, JetBrains Mono for all figures; ink `#191713` on paper `#F3EEE4`, hairlines `rgba(25,23,19,.14)`, one oxide-red signal `#C3402C`; dense 36px table rows, no cards, no gradients, no purple, no glass, 120–180ms ease-out motion.

---

## Palette (light is default)

```
--paper:      #F3EEE4   /* page bg */
--paper-2:    #EAE3D5   /* inset */
--panel:      #FBF7EE   /* chart, drawer, popover */
--ink:        #191713   /* primary text, primary btn */
--ink-2:      #3B3831   /* body */
--muted:      #6B665B   /* secondary */
--faint:      #928B7D   /* labels, units */
--rule:       rgba(25,23,19,.14)  /* hairlines */
--signal:     #C3402C   /* cost, primary action, active */
--moss:       #5E6B3C   /* savings, healthy */
--ochre:      #B9852F   /* warning */
--slate:      #4D6270   /* neutral info */
```

Dark mode: swap to warm charcoal `#14130F`, ink `#F1ECE1`, rule `rgba(241,236,225,.12)`, signal `#D9573F`.

---

## Type

| Role | Face | Use |
|------|------|-----|
| Voice | Instrument Serif | wordmark, page title, hero total |
| Work | Instrument Sans | nav, labels, body, buttons, table |
| Evidence | JetBrains Mono | **all numbers, units, IDs, timestamps, axis ticks** |

Self-host all three. No CDN. All numbers `font-variant-numeric: tabular-nums`, right-aligned.

---

## Layout scaffold

```
Top bar (56px) ─────────────────────────────────────────────── 1px rule
Section header ── period label, one sentence, hero total
KPIs ─────────── 3 inline stats, no cards
Table ────────── the hero: model | tokens | requests | cost | 7d spark
Charts ───────── two panels: daily cost + cost by model (small multiples)
Status line ──── mono: branch · host · latency · version
```

- Max-width 1320px, 32px gutters, 8px rhythm.
- Section gaps 48–72px, 1px hairlines between.
- Table rows 36px, header 28px mono uppercase `--faint`, no zebra.
- One primary action per screen; ink-filled unless it spends money.
- Radius: 2px / 6px / 10px. No larger.

---

## Components cheat sheet

| Component | Spec |
|-----------|------|
| Button | 32px, 6px, 1px rule. Default: transparent + ink. Primary: ink fill. Signal fill = destructive/cost. No shadow/glow/gradient. |
| Input/Select | 32px, paper bg, 1px rule. Focus: 2px signal outline. |
| Status | 6px dot + 10px mono UPPERCASE. Colours: moss/ochre/signal/faint. No pill. |
| Table | Sort: small ▲▼ in mono. Hover: `rgba(195,64,44,.04)`. Selected: 2px signal left rule. |
| Panel/Drawer | `--panel`, 1px rule, 10px radius, inset highlight. No drop shadow. No nesting. |
| Empty state | One sentence + one action. No illustration, no orb, no magic icon. |

---

## Charts

- 1.5px lines, 1px grid at 8% ink, no border, **no legend**.
- Labels at end of line in series colour.
- One annotation per chart, serif italic, dashed signal rule.
- Area: flat 8% tint or none. Never gradient.
- Categorical: moss, ochre, slate, rose, ink. Sequential: one hue, 4 steps.
- Small multiples share scale; highlight one panel.
- Tooltip: paper, 1px rule, mono, 120ms fade.

---

## Motion

- Hover/press 120ms, drawer/popover 180ms, entrance 240ms (4–8px rise).
- `cubic-bezier(.2,.8,.2,1)`. Opacity + transform only.
- No bounce except dragging. No count-up on load.
- Respect `prefers-reduced-motion`.

---

## Language

Terse, factual, lowercase labels. Ledger clerk, not growth marketer.

| Don't | Do |
|-------|----|
| Supercharge your AI insights | What this month cost. |
| No data available | No events in this range. |
| AI-powered analytics | *(delete)* |
| Unlock savings | Cache saved $12.40 |
| Oops! Something went wrong | Import failed: missing `usage.jsonl` |
| Let's get started | Import events |

No exclamation marks. No "magic", "effortless", "seamless".

---

## Banned (from the house Purple List)

Purple/indigo · gradient text · radial glows · glassmorphism · pill badges · emoji/sparkle icons · bento grids · icon soup · drop shadows on static panels · decorative colour · count-up animations · "AI-powered" copy · radius 20px+.

---

## Acceptance checklist (verify before shipping)

- [ ] Grayscale screenshot still has clear hierarchy
- [ ] Exactly one accent colour on screen
- [ ] No gradient anywhere
- [ ] Every number tabular + aligned
- [ ] Table is the most prominent element after hero
- [ ] No card inside a card
- [ ] No shadow on static surface
- [ ] All text ≥ 4.5:1 (large ≥ 3:1)
- [ ] Keyboard reaches every action; `⌘K` opens palette
- [ ] Reduced-motion removes non-essential transitions
- [ ] Copy passes "ledger clerk" test

---

## Files in this repo

- `DESIGN.md` — full brief (source of truth)
- `../design/PHILOSOPHY.md` — house philosophy
- `../design/REFERENCES.md` — where elements came from
- `../design/reference-wall.html` — visual picker (open in browser)

---

## If the agent asks for more context

> "Follow `DESIGN.md` literally. The current dashboard uses indigo gradients, purple radials, glass cards, gradient-clipped hero numbers, and pill badges — all of which are explicitly banned. Replace the KPI card grid with a dense table. Replace the legend-heavy charts with direct labels and small multiples. Use the exact palette and type tokens above. Light mode first."