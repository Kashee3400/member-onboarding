# Portal design rules

Staff use this all day, often on ordinary laptops. Every page should be quick to read,
calm, and fully usable from the keyboard. If a page needs explaining, simplify the page.

## Look

- **Sharp corners.** Radius is 0 everywhere. Only avatars and status dots stay round.
- **Fields lift.** Every field is a sharp box that rises with a brand-coloured shadow while
  in use. The kit does this: never restyle a field by hand.
- **Colour has a job.** `primary` is for the main action and the current place. Amber means
  waiting, green done, red stopped. Everything else is neutral.
- **Colours come from tokens only**: `bg-card`, `text-muted-foreground`, `border`,
  `text-primary`. Never `slate-*`, `#hex` or `white`: they break dark mode and an
  organization's own brand colours.
- **One primary button per screen.** Other actions are `outline` or `ghost`.
- **Numbers line up.** Codes and amounts use `tabular-nums`; 16-digit codes use `font-mono`.

## Layout

- Each page: `PageHeader` (title, one plain sentence, actions), then the content.
- Content sits in `Card`s with `p-4` or `p-5`, and `gap-4` between them.
- Long forms use a two-column grid on wide screens, with fields grouped under plain headings.
- Must work at 375px wide with no sideways page scroll. Tables scroll inside their card.

## States

Every data view handles loading (`Skeleton`, shaped like the content), empty (`EmptyState`,
saying what will appear there and what to do), and errors (`ErrorState` with retry). A blank
area is a bug.

## Components

Use the kit before writing anything: `components/ui/*`, and from `components/common/`:
`DataTable` for every list, `Listbox` and `AsyncSelect` rather than a native select,
`DatePicker` rather than a date input, `ReasonDialog` for anything needing a reason,
`StatusBadge`, `PageHeader`, `EmptyState`, `ErrorState`, `SearchBox`. No native `<select>`,
`alert()` or `confirm()`. Success and failure use `toast` from `sonner`.

## Keyboard

- Everything clickable works with Tab and Enter, with a visible focus ring.
- `useListKeys` from `lib/shortcuts.ts` gives review queues J / K / A / D / Enter. Mark
  buttons with `data-shortcut="approve"`, `"dismiss"` or `"open"`.
- Anything new goes into the list in `components/shell/shortcuts-help.tsx`.

## Words

Plain English, short sentences, no jargon. Say what happened and what to do next:
"Passbook photo is missing. Ask the facilitator to add it." Show `mpp_ex_code` (our
`Mpp.code`), never the internal `source_code`.

Permissions: `useCan` hides what someone can't do. The API still enforces it.
