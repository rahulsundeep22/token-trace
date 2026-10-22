# TokenTrace — design brief v1.0

**Concept: the ledger, not the cockpit.**
TokenTrace is a cost ledger that happens to be alive: warm paper, ink, one red signal, mono
figures, hairline rules. It should look printed, not generated. The current indigo-gradient
dashboard is the exact thing this replaces.

This file is self-contained. Drop it in the repo root as `DESIGN.md` and tell the coding
agent to follow it. House philosophy: `../design/PHILOSOPHY.md`.

---

## 0 · Non-negotiables

- No purple or indigo. No gradient text. No radial glows. No glass cards.
- One accent only: oxide red. Green and amber are semantic, never decorative.
- The table is the primary interface. Cards are not the default layout unit.
- All numbers are tabular and monospace; units are small, muted, and adjacent.
- Every screen must survive grayscale.
- Light mode is the default. Dark mode is warm charcoal, never blue-black.

---

## 1 · Palette

| Token | Hex | Use |
| --- | --- | --- |
| `--paper` | `#F3EEE4` | page background |
| `--paper-2` | `#EAE3D5` | inset areas, code blocks |
| `--panel` | `#FBF7EE` | chart panel, drawer, popover |
| `--ink` | `#191713` | primary text, primary button |
| `--ink-2` | `#3B3831` | body text |
| `--muted` | `#6B665B` | secondary text |
| `--faint` | `#928B7D` | labels, units, disabled |
| `--rule` | `rgba(25,23,19,.14)` | hairlines, borders |
| `--signal` | `#C3402C` | cost, primary action, active state |
| `--moss` | `#5E6B3C` | savings, healthy, positive delta |
| `--ochre` | `#B9852F` | warning, approaching limit |
| `--slate` | `#4D6270` | neutral info, secondary series |

Dark mode:

| Token | Hex |
| --- | --- |
| `--paper` | `#14130F` |
| `--paper-2` | `#1B1915` |
| `--panel` | `#1D1B15` |
| `--ink` | `#F1ECE1` |
| `--muted` | `#A29B8D` |
| `--rule` | `rgba(241,236,225,.12)` |
| `--signal` | `#D9573F` |

Do not add a second accent. If something needs emphasis, use weight, size, or a rule.

---

## 2 · Type

| Role | Face | Rules |
| --- | --- | --- |
| Voice | **Instrument Serif** | wordmark, page title, hero total. One or two uses per screen. |
| Work | **Instrument Sans** | nav, labels, body, buttons, table text. |
| Evidence | **JetBrains Mono** | numbers, units, IDs, timestamps, axis ticks, status. |

Self-host all three (or use the Google Fonts files locally). No CDN at runtime; this is a
local-first tool.

Scale: `11 / 12 / 13 / 15 / 18 / 24 / 32 / 56`
- Page title: 32–40px serif, `-0.03em`, weight 400.
- Hero total: 56–64px serif, `-0.04em`.
- Body: 13–15px sans, 1.5 line-height.
- Labels: 9–10px mono, uppercase, `0.14em` tracking, `--faint`.
- Numbers: mono, `font-variant-numeric: tabular-nums`, right-aligned in columns.

No all-bold screens. Weights: 400 body, 500 UI, 600 only for the single hero figure.

---

## 3 · Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│ TokenTrace               ● local       ⌘K       1–22 Oct ▾   Export │ 56px
├─────────────────────────────────────────────────────────────────────┤
│ PERIOD · 22 DAYS                                                    │
│ What this month cost.                                               │
│                                                                     │
│ $184.20            Tokens 14.2M    Requests 8,412    Cache 62%      │
│ +12.4% vs prev     ─────────────   ──────────────    ─────────       │
├─────────────────────────────────────────────────────────────────────┤
│ MODEL              TOKENS     REQUESTS     COST       7D            │
│ claude-sonnet       2.4M          412     $18.20     ╱╲╱           │
│ gpt-5               1.8M          318     $14.60     ╱╲╱           │
│ deepseek-v4         4.1M          902      $3.12     ╱╲╱           │
├─────────────────────────────────────────────────────────────────────┤
│ Daily cost                                        Cost by model      │
│ [ line chart, direct labels ]                     [ small multiples ]│
├─────────────────────────────────────────────────────────────────────┤
│ main · 127.0.0.1 · 12ms · v0.4.2 · last scan 09:41                  │ 28px
└─────────────────────────────────────────────────────────────────────┘
```

- Max width 1320px, 32px gutters. 4px base, 8px rhythm.
- Top bar 56px, 1px bottom rule. No shadow.
- Section gaps 48–72px; hairlines between sections.
- Table rows 36px; header 28px; no zebra striping.
- One primary action per screen. It is ink-filled, not red, unless the action spends money.
- Radius: 2px (marks), 6px (buttons/inputs), 10px (drawer/panel). Nothing larger.

---

## 4 · Components

**Button** — 32px high, 6px radius, 1px rule. Default: transparent with ink text. Primary:
ink fill, paper text. Signal fill is reserved for a destructive or cost action. No shadow,
no glow, no gradient.

**Input / select** — 32px high, paper background, 1px rule. Focus: 2px signal outline,
2px offset. No inner shadow.

**Status** — 6px dot + 10px mono uppercase label. No pill background. Colours: moss
(healthy), ochre (warning), signal (over budget), faint (idle).

**Table** — the hero. Header in 9px mono uppercase, `--faint`; rows 36px; 1px bottom rule;
numbers right-aligned mono; hover row `rgba(195,64,44,.04)`; selected row a 2px signal left
rule. Sort indicator is a small ▲/▼ in mono, not an icon.

**Panel** — only for a chart, drawer, or popover. `--panel`, 1px `--rule`, 10px radius,
`inset 0 1px rgba(255,255,255,.5)` in light mode. No drop shadow. No nested panels.

**Drawer** — 420px wide, paper background, 1px left rule, 180ms slide. Header: model name
in serif, close button in mono `ESC`. Body: definition list with mono values.

**Empty state** — one sentence and one action. No illustration, no orb, no "magic" icon.

---

## 5 · Charts

- Line 1.5px; grid 1px at 8% ink; no chart border, no legend.
- Series labels at the end of the line, in the series colour.
- One annotation per chart, in serif italic, with a 1px dashed signal rule.
- Area fill: flat 8% tint or none. Never a gradient.
- Categorical: moss, ochre, slate, rose, ink. Sequential: one hue, four steps.
- Small multiples share a scale. Highlight one panel; leave the rest ink.
- Tooltip: paper background, 1px rule, mono values, no shadow, 120ms fade.

---

## 6 · Motion

- Hover/press 120ms; drawer/popover 180ms; page entrance 240ms, 4–8px rise.
- Easing `cubic-bezier(.2,.8,.2,1)`. No bounce except dragging.
- Animate opacity and transform only. No count-up numbers on load.
- Respect `prefers-reduced-motion`.

---

## 7 · Language

Terse, factual, lowercase labels. The interface should sound like a ledger clerk, not a
growth marketer.

| Don't | Do |
| --- | --- |
| Supercharge your AI insights | What this month cost. |
| No data available | No events in this range. |
| AI-powered analytics | (delete) |
| Unlock savings | Cache saved $12.40 |
| Oops! Something went wrong | Import failed: missing `usage.jsonl` |
| Let's get started | Import events |

No exclamation marks. No "magic", "effortless", "seamless". Errors say what happened and
what to do next.

---

## 8 · Screens to rebuild

1. **Dashboard** — header, one hero total, three inline stats, dense model table, two charts,
   status line. No KPI card grid.
2. **Sessions** — full-width table, filters as a single row of text controls, pagination in
   mono. Row click opens the drawer.
3. **Model detail** — serif model name, one cost total, 7/30-day chart, per-session table,
   source breakdown. Same hairlines.
4. **Import** — drop zone with a 1px dashed rule, mono progress log, no spinner-only state.
5. **Settings** — definition list, not cards. Paths and versions in mono.

---

## 9 · Banned

Purple/indigo accents · gradient text · radial aurora glows · glassmorphism · pill badges
over headings · emoji icons · sparkle/wand icons · equal-weight bento grids · icon soup ·
drop shadows on static panels · decorative colour · count-up animations · "AI-powered"
copy · three accent hues in one view · radius 20px+ on everything.

---

## 10 · Acceptance checklist

- [ ] Screenshot in grayscale still has clear hierarchy.
- [ ] Exactly one accent colour on screen.
- [ ] No gradient anywhere except a photographic asset (none expected).
- [ ] Every number is tabular and aligned.
- [ ] The table is the most prominent element after the hero total.
- [ ] No card inside a card.
- [ ] No shadow on a static surface.
- [ ] All text passes 4.5:1; large text 3:1.
- [ ] Keyboard reaches every action; `⌘K` opens the palette.
- [ ] Reduced-motion mode removes all non-essential transitions.
- [ ] Copy passes the "ledger clerk" test: factual, no exclamation marks.

---

## 11 · One-sentence brief for the other agent

> Rebuild TokenTrace as a warm paper ledger: Instrument Serif for the wordmark and hero
> total, Instrument Sans for UI, JetBrains Mono for all figures; ink `#191713` on paper
> `#F3EEE4`, hairlines `rgba(25,23,19,.14)`, one oxide-red signal `#C3402C`; dense 36px
> table rows, no cards, no gradients, no purple, no glass, 120–180ms ease-out motion.
