# Interface Design System — Контентфабрика (dashboard)

Light workspace for Russian-speaking creators and marketers.
UI language is **Russian** ("Контентфабрика"; "OpenShorts" only as EN codename).
React 18 + Vite + Tailwind. The authenticated application uses a light theme.

## Direction & feel
Calm, dense-but-breathable workspace. One confident brand accent; structure carried
by subtle layering, not loud color. Color that isn't status or data is noise.

## Core rule: ONE accent, data is the exception
- **Single brand accent = muted violet.** Use it for the main action, active step,
  selection, links and focus. Secondary actions use neutral surfaces.
- **Colour is allowed only when it encodes data or status** (see scales below).
  When in doubt, it's an accent → violet.

## Tokens (AppChrome.css)
- Workspace `--app-white` `#fff`, chrome `--app-toolbar` `#fbfbfc`, secondary surface `--app-canvas` `#f0f1f3`.
- Main text `--app-ink` `#242631`, secondary text `--app-muted` `#545967`.
- Accent `--app-accent` `#574585`, selected surface `--app-selected` `#f0edf4`.
- Hairline `--app-line` `#dfe1e7`, field boundary `--app-field` `#8b90a0`.
- AI Shorts and the storyboard editor reuse these tokens in their scoped stylesheets.

## Depth
Separate regions and lists with hairlines. Use a secondary surface for toolbars
and previews. Keep dark backing around footage when it improves legibility.

## Radius & spacing
- Fields and buttons use `--app-radius` (5 px).
- Spacing: Tailwind 4px scale. Nav rows `px-3 py-2.5 space-y-1.5`. Panel padding `p-5`/`p-6`.

## Key patterns
- Use one filled primary button per view and a visible violet focus outline.
- Sidebar and mobile navigation share `navItems` and mark the active item with `aria-current`.
- Show progress as a flat sequence with the current step underlined. Put missing credentials beside the action that requires them.

## Media player — approved reusable pattern (2026-10-15)

Use `src/components/MediaPlayer.jsx` with its scoped `MediaPlayer.css` for playable
HTML audio/video throughout the dashboard, not browser-native `controls`. Reuse it
for voice takes, music previews, gallery/detail views and finished videos. Leave
decorative muted videos and the separate Remotion Player integration alone.

- **Appearance:** the audio controls use the light workspace palette. Video uses
  a dark backing for controls over footage. Progress and
  duration come from the actual media element. Until metadata arrives, the time
  reads `0:00` and seeking is disabled; do not invent a duration for screenshots.
- **Sizing:** playback/mute/fullscreen buttons are `44 × 44px`; the optional central
  video play button is `64 × 64px`. Audio padding is `8px`, gaps are `12px` or `8px`
  with `compact`. Individual voice takes currently use
  `className="w-full max-w-[280px]"`; `compact` alone does not set a width. Caller
  sizing stays authoritative: never add a base `max-width` that overrides these
  utilities. Keep narrow layouts usable rather than shrinking the hit targets.
- **Layout contract:** `kind="audio"` selects audio; video is the default. `src`,
  `poster`, `label`, `preload`, `disabled`, `muted` and `defaultVolume` describe the
  media. `className` sizes the wrapper; `mediaClassName` controls the media itself
  (for example, `object-contain`). All visible/accessibility labels are Russian.
- **Controls:** play/pause, elapsed/total time, a seek range and mute. Hovering or
  focusing the sound control reveals its volume slider; Tab reaches the slider,
  Escape closes it and returns focus to the sound button. Video also provides a
  fullscreen button using the browser Fullscreen API or the supported WebKit
  media fallback; availability remains browser-dependent.
- **Keyboard:** when the player itself is focused, Space/K toggles playback,
  left/right arrows seek by five seconds within real duration, and M toggles mute.
  These shortcuts do not intercept buttons, inputs, textareas, selects, links or
  editable content; nested controls retain their normal keyboard behavior.
- **States and responsiveness:** show actual buffering and readable load/playback
  errors, visible keyboard focus, and disabled controls for missing/disabled
  sources. Disabling pauses playback. Container queries reduce gaps and hide the
  secondary video total-time display at widths up to `300px`; do not remove play,
  mute or fullscreen controls to make a narrow card fit.
- **Integration:** the forwarded ref remains the underlying `HTMLMediaElement`,
  not the wrapper. Preserve existing media props and parent playback/metadata/
  time/volume/error callbacks when using the component. CSS stays under the
  `cf-media-player` prefix; do not globally restyle every `audio` or `video` tag.
- **Checks:** `src/components/MediaPlayer.test.mjs` covers custom markup, source/
  poster, unavailable states, time/seek helpers, keyboard exclusions, shared
  callers and the sizing regression. Verify real playback/seek/volume plus desktop
  and narrow-screen layout in a browser before accepting visual changes.

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
