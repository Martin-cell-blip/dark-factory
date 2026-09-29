# Pocketful screens — design note

Character: a calm, trustworthy consumer-finance app. Quiet neutrals, one green for money
you can act on, and colour reserved for meaning (status and feedback). Every screen is
built from the tokens below (`pocketful/web/assets/app.css`, `:root`).

## Colour tokens (contrast checked, WCAG 2.1)

| Token | Value | Used for | Contrast |
|---|---|---|---|
| `--canvas` | `#F4F6F8` | page background | — |
| `--surface` | `#FFFFFF` | cards, inputs | — |
| `--ink` | `#15202B` | body text, amounts | 16.5:1 on surface, 15.2:1 on canvas |
| `--ink-muted` | `#4B5563` | labels, secondary numbers, timestamps | 7.6:1 on surface, 7.0:1 on canvas |
| `--line` | `#D9DEE5` | card and list dividers (decorative) | — |
| `--line-strong` | `#8A94A3` | input borders (non-text, 3:1 required) | 3.1:1 on surface |
| `--primary` | `#0B6B4E` | primary buttons, headline number accent, links | white on it 6.5:1; as text 6.5:1 |
| `--primary-hover` | `#075A41` | primary hover/active | white on it 8.2:1 |
| `--header` | `#10261F` | top bar | white 15.9:1, `--header-muted` `#B7C9C1` 9.2:1 |
| `--focus` | `#1D4ED8` | focus ring (3 px outline) | 6.7:1 on surface, 6.2:1 on canvas; `#93C5FD` on header 8.8:1 |
| `--success-ink` / `--success-bg` | `#0A5A3F` / `#E6F4EC` | successful | 7.3:1 |
| `--refused-ink` / `--refused-bg` | `#9B1C1C` / `#FDECEC` | refused, error | 7.1:1 |
| `--uncertain-ink` / `--uncertain-bg` | `#7A4300` / `#FFF3D6` | uncertain outcome | 7.2:1 |
| `--held-ink` / `--held-bg` | `#3730A3` / `#EEF0FF` | held funds, open holds | 8.8:1 |
| `--pending-ink` / `--pending-bg` | `#1E4E8C` / `#E8F1FB` | pending requests | 7.3:1 |
| `--neutral-ink` / `--neutral-bg` | `#374151` / `#EEF0F3` | closed states (declined, cancelled, voided, expired) | 9.0:1 |

Colour is never the only signal: every status also has a word, and feedback boxes have
an icon glyph and a title.

## Type scale

System UI font stack (nothing loaded from the network); amounts use tabular numerals.

| Step | Size / line height | Weight | Used for |
|---|---|---|---|
| `--text-xs` | 12 / 16 px | 500 | badges, captions |
| `--text-sm` | 14 / 20 px | 400–600 | labels, secondary numbers, list meta |
| `--text-md` | 16 / 24 px | 400 | body, inputs (16 px stops mobile zoom) |
| `--text-lg` | 20 / 28 px | 600 | card titles, list amounts |
| `--text-xl` | 28 / 34 px | 700 | page titles |
| `--text-hero` | 40 / 44 px (32 px on phones) | 700 | available funds, the headline number |

## Spacing, shape

4 px base: `--space-1` 4, `--space-2` 8, `--space-3` 12, `--space-4` 16, `--space-5` 24,
`--space-6` 32, `--space-7` 48. Cards: 12 px radius, 24 px padding (16 px on phones), 1 px
`--line` border. Inputs and buttons: 8 px radius, minimum 44 px tall (touch target).

## Layout

- **Phone (375 px, up to 719 px):** one column. The top bar holds the brand and the signed-in
  person; the four destinations sit in an equal-width tab row under it (no horizontal
  scrolling). Cards stack: wallet, a "Jump to your activity" link, pay, request, hold, activity. Long
  handles and notes wrap.
- **Desktop (720 px and up, content max 1080 px, centred):** the tab row joins the top bar.
  Home is two columns: wallet and the three action forms on the left (minmax 320 px), the
  activity feed on the right. Requests and holds show incoming and outgoing side by side
  from 960 px.

## States

| State | How it looks | How it behaves |
|---|---|---|
| Available | Hero number in `--ink` with a "Available to spend" label, green dot | The largest amount on screen; updates after every successful action and on refresh |
| Held | `--held` chip "On hold 20.00 EUR" beside the total; absent when zero | Follows the same refresh rules as available |
| Total | Secondary line "Total balance" in `--ink-muted`, `--text-sm` | Always shown; equals available when nothing is held |
| Pending | `--pending` badge "Pending" on requests; open holds use the held badge "On hold" | Pay/decline or cancel buttons appear only on pending items |
| Loading | The top bar, navigation and Log out appear at once; the person's name and every card show skeleton bars (animated shimmer, reduced-motion aware, `aria-busy`) until the first read lands; submit buttons show "Sending…" and are disabled | Nothing is double-submitted while a request is in flight |
| Unreachable | Inside the normal shell: a refused-coloured card "Pocketful can't be reached right now" with a Try again button | Navigation and Log out keep working |
| Successful | `--success` box with ✓ and a sentence ("Sent 15.00 EUR to ben") | Form keeps its values; data refreshes after the write succeeds |
| Refused | `--refused` box with ! and the reason in plain words | Inputs are kept; balance and lists refresh |
| Uncertain | `--uncertain` box with ? and dashed border: "We couldn't confirm…" | Submitting the unchanged form retries with the same key; never shown as a refusal |
| Empty | Centred muted illustration-free message with a hint ("No activity yet — payments you can see appear here") | Replaces the list for the feed; beside the empty lists on requests and holds |
| Error | Refused-coloured box at the top of the card ("Couldn't load your latest activity") pointing to Refresh | The last good data stays visible (stale), marked "Not up to date" |
| Stale | Muted "Not up to date — Refresh" note under the wallet | Cleared by the next successful refresh |
| Hold expiry | "Expires 30 Sept 2026, 03:18 (in 2 h)" or "Expired …" in local time, beside the exact RFC 3339 time | One wording for open and closed holds |
| Closed statuses | `--neutral` badges: Paid (success colours), Declined, Cancelled, Released (voided), Collected (captured), Expired | No action buttons |

## Controls and access

Every input has a visible `<label>`. Focus is a 3 px `--focus` outline with 2 px offset on
every control (`:focus-visible`). Primary action: filled `--primary` button; secondary:
outlined; destructive (decline, cancel, release): outlined in `--refused-ink`. Status and
feedback regions are `role="status"` / `role="alert"` so screen readers announce them.
