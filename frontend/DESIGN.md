# Leovee — design system

Arabic-first, RTL-native, dark-primary. The rules below are the ones a review
cannot reliably catch, so each is enforced by `src/designRules.test.ts` or by
the token layer itself; this document explains *why*, the tests enforce *that*.

Ported from AiChart's `DESIGN.md`, minus the vocabulary belonging to subsystems
Leovee excludes (execution, brokers, notifications).

## Tokens

Live in `src/styles/tokens.css`, consumed as semantic Tailwind classes
(`text-buy`, `bg-warning/10`, `border-border`) — never raw hex in components.
The guard fails any `.tsx` carrying a `#rrggbb` literal.

| Meaning | Token | Light | Dark | Note |
|---|---|---|---|---|
| Surface | `--background` / `--card` | `#ffffff` | `#0f1419` / `#1a2332` | cards elevate by border, not shadow |
| Text | `--foreground` | `#000000` | `#f5f5f5` | |
| Secondary text | `--muted-foreground` | `#404040` | `#a3a3a3` | AA on its surface |
| Border | `--border` | `#e5e5e5` | `#1f2937` | 1px, everywhere |
| **Buy / long** | `--buy` | `#15803d` | `#22c55e` | trade **direction** only |
| **Sell / short** | `--sell` | `#dc2626` | `#ef4444` | trade **direction** only |
| Healthy status | `--success` | same as buy | | separate token on purpose — status must not drag if the trading palette is retuned |
| Warning / pending | `--warning` | `#d97706` | `#f59e0b` | conditional plans, approaching levels |
| Info | `--info` | `#0284c7` | `#38bdf8` | |
| Destructive | `--destructive` | `#dc2626` | `#ef4444` | irreversible actions only |

## Non-negotiables

- **Buy/sell colours mean trade direction.** Never reuse them as generic
  success/error. A green "saved" toast next to a green BUY chip teaches the eye
  that green means "fine", and the one place that lesson gets applied is the
  one place it costs money.
- **Tradability chips:** `now` → buy tones, `soon` → warning tones,
  `watch_only` → muted, and `rejected` **is never rendered as a card at all** —
  showing it invites someone to take it.
- **Logical properties only** (`ms-`/`me-`/`ps-`/`pe-`/`text-start`/`text-end`/
  `border-s`/`border-e`). Arabic is the default locale; a physical `ml-4` is
  invisible in an LTR review and wrong for the majority of users. Enforced.
- **No static quick-action buttons in chat.** Canned suggestion chips teach the
  user the agent only understands those, and rot the moment the pipeline
  changes underneath them. Enforced.
- **Every user-facing string goes through `t()`.** Keys are typed
  (`TranslationKey`), Arabic is the source dictionary, and the parity test
  fails when `ar`/`en` drift in either direction.
- **Tests assert `data-testid`, never display text.** Copy changes must not
  break tests; a test coupled to a sentence turns every wording improvement
  into a test-fixing session.

## Direction

`LocaleProvider` sets `dir` and `lang` on `document.documentElement` — the
root, not a wrapper div, so portals and overlays inherit the direction too.
Anything that must not mirror (price charts, numerals) opts out explicitly
with `dir="ltr"` on the element, with a comment saying why.

## Components

- **Cards**: `rounded-lg border border-border bg-card p-4` — elevation by
  border, not shadow.
- **Chips / badges**: `rounded-full border px-2 py-0.5 text-[11px]` with the
  semantic tone classes.
- **Numbers**: prices and R-multiples render in Latin digits regardless of
  locale (they are read against the chart's axis, which is Latin-digit), inside
  a `dir="ltr"` span when embedded in Arabic prose.
