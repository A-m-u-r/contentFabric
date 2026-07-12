# Interface Design System — Контентфабрика (dashboard)

Dark, focused, "creative studio" tool for a Russian-speaking solo creator/marketer.
UI language is **Russian** ("Контентфабрика"; "OpenShorts" only as EN codename).
React 18 + Vite + Tailwind. Dark theme only.

## Direction & feel
Calm, dense-but-breathable workspace. One confident brand accent; structure carried
by subtle layering, not loud color. Color that isn't status or data is noise.

## Core rule: ONE accent, data is the exception
- **Single brand accent = violet.** Every button, focus ring, link, active tab,
  selection state, and decorative accent uses violet. Do **not** introduce blue,
  emerald, teal, cyan as generic accents.
- **Colour is allowed only when it encodes data or status** (see scales below).
  When in doubt, it's an accent → violet.

## Tokens (tailwind.config.js + index.css)
- `background` `#09090b` · `surface` `#18181b`
- `primary` = `accent` = `#8b5cf6` (Tailwind **violet-500**). `bg-primary`, `text-primary`,
  focus rings and the `violet-*` scale all agree. Hover = `violet-600`. Lighter text = `violet-400`.
- Text hierarchy: `text-white` / `text-zinc-300` / `text-zinc-400` / `text-zinc-500-600`.
- Borders: `border-white/10` standard, `/5` softer, `/20` emphasis. Never harsh solid hex borders.

## Depth
Surface-tint + hairline borders (no heavy shadows). Panels = `.glass-panel`
(`bg-surface/50 backdrop-blur-xl border-white/10 rounded-2xl shadow-xl`). Inputs are
inset: `bg-white/5` / `bg-black/20`, darker than their surroundings.

## Radius & spacing
- Radius: inputs/buttons `rounded-xl`, cards/panels `rounded-2xl`, pills `rounded-full`.
- Spacing: Tailwind 4px scale. Nav rows `px-3 py-2.5 space-y-1.5`. Panel padding `p-5`/`p-6`.

## Key patterns
- **Buttons:** `.btn-primary` (`bg-primary hover:bg-violet-600 rounded-xl shadow-primary/20`),
  `.btn-secondary`. Never `hover:bg-blue-*` on a `bg-primary` button.
- **Inputs:** `.input-field`, focus `border-primary/50 ring-primary/50`.
- **Sidebar / mobile bar:** driven by ONE `navItems` array (never hand-write per item).
  Active = `bg-primary/10 text-primary` (`NAV_ACTIVE`), inactive =
  `text-zinc-400 hover:text-white hover:bg-white/5` (`NAV_INACTIVE`). Set `aria-current`
  + `aria-label`. Mobile grid columns = `navItems.length` (inline `gridTemplateColumns`).
- **Tab headers:** icon chip `bg-gradient-to-br from-violet-500 to-fuchsia-500` (the one
  established brand gradient) or `bg-primary/10 text-primary`.
- **Selected state:** `border-primary/50 bg-primary/10 text-violet-200`.

## Data / status scales — KEEP these coloured (do NOT flatten to violet)
- **Status:** success = `green-400/500` (feature checkmarks may use `emerald-400`),
  warning = `amber`, error = `red`. Info panels use violet, not blue.
- **Price/cost tiers** (mode & model tiles): lowcost = green, standard = blue,
  premium/pro = violet, top/Veo = amber. Cheap→expensive reads at a glance.
- **Script segment types:** hook = red, problem = yellow, solution = green, cta = blue.
- **Platform brand colours:** TikTok = cyan, YouTube = red, Instagram = pink.
- **Content-plan goals** (`GOAL_STYLES`): прогрев = amber, вовлечение = blue,
  доверие = emerald, продажа = violet.

## Copy
Russian everywhere in-app. Watch for stray English in legacy surfaces
(ThumbnailStudio / ResultCard still have some — translate when touched).

## Verifying UI here
The app is hash-routed: dashboard lives at `/#app` (default view is the marketing
Landing). Auth-gated (`if (!authUser)`), so a running backend + login is needed for the
full shell; for a quick look, screenshots may hang in this env — verify via computed
styles with the browser JS tool (`getComputedStyle`) instead.
