"use client";

import {
  endOfMonth,
  endOfYear,
  format,
  isValid,
  parse,
  startOfDay,
  startOfMonth,
  startOfYear,
  subDays,
  subMonths,
} from "date-fns";
import { CalendarDays, CalendarRange, ChevronLeft, ChevronRight, Clock, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Matcher } from "react-day-picker";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

/*
 * The panel's date boxes. They hold the same strings the browser's own inputs did —
 * "YYYY-MM-DD", "YYYY-MM-DDTHH:mm" (local time) and "YYYY-MM" — so a page swaps
 * `<Input type="date">` for one of these and nothing else changes.
 */

const DAY = "yyyy-MM-dd";
const STAMP = "yyyy-MM-dd'T'HH:mm";
const MONTH = "yyyy-MM";

function read(value: string | undefined | null, pattern: string): Date | undefined {
  if (!value) return undefined;
  const d = parse(value.slice(0, pattern === STAMP ? 16 : pattern.length), pattern, new Date());
  return isValid(d) ? d : undefined;
}

const today = () => new Date();
/** The years the month/year dropdowns offer. */
const FIRST = new Date(2020, 0, 1);
const LAST = new Date(today().getFullYear() + 5, 11, 31);

function limits(min?: string, max?: string) {
  const lo = read(min, DAY);
  const hi = read(max, DAY);
  const disabled: Matcher[] = [];
  if (lo) disabled.push({ before: lo });
  if (hi) disabled.push({ after: hi });
  return { lo, hi, disabled };
}

type Size = "default" | "sm";

/** Looks like the panel's text boxes: an icon, the value (or a hint), a clear button. */
function Trigger({
  icon: Icon,
  text,
  placeholder,
  size,
  onClear,
  className,
  ...props
}: {
  icon: typeof CalendarDays;
  text: string;
  placeholder: string;
  size: Size;
  onClear?: () => void;
  className?: string;
  id?: string;
  disabled?: boolean;
  "aria-invalid"?: boolean;
  "aria-label"?: string;
}) {
  return (
    <div className={cn("relative flex", size === "sm" ? "w-40" : "w-full", className)}>
      <PopoverTrigger
        {...props}
        className={cn(
          "flex w-full min-w-0 items-center gap-2 rounded-none border border-input bg-transparent px-2 text-left transition-colors outline-none dark:bg-input/30",
          "hover:border-ring/60 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 data-popup-open:border-ring",
          "disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive",
          size === "sm" ? "h-8 text-xs" : "h-9 text-sm",
          onClear && text ? "pr-7" : "",
        )}
      >
        <Icon className="size-4 shrink-0 text-muted-foreground" />
        <span className={cn("min-w-0 flex-1 truncate", !text && "text-muted-foreground")}>{text || placeholder}</span>
      </PopoverTrigger>
      {onClear && text && !props.disabled ? (
        <button
          type="button"
          aria-label="Clear"
          onClick={onClear}
          className="absolute top-1/2 right-1.5 -translate-y-1/2 p-0.5 text-muted-foreground hover:text-foreground"
        >
          <X className="size-3.5" />
        </button>
      ) : null}
    </div>
  );
}

function Footer({ children }: { children: ReactNode }) {
  return <div className="flex items-center justify-between gap-2 border-t pt-2">{children}</div>;
}

type Common = {
  id?: string;
  placeholder?: string;
  disabled?: boolean;
  /** "sm" is the compact box used in table filters. */
  size?: Size;
  className?: string;
  /** Show the clear (×) button. On by default. */
  clearable?: boolean;
  "aria-invalid"?: boolean;
  "aria-label"?: string;
};

// --- one day ---------------------------------------------------------------------------

/** Pick a day. `value` / `onChange` are "YYYY-MM-DD" ("" when empty); `min` / `max` too. */
export function DatePicker({
  value,
  onChange,
  min,
  max,
  placeholder = "Pick a date",
  size = "default",
  clearable = true,
  className,
  ...rest
}: Common & { value: string | undefined | null; onChange: (v: string) => void; min?: string; max?: string }) {
  const [open, setOpen] = useState(false);
  const picked = read(value, DAY);
  const { lo, hi, disabled } = limits(min, max);
  const now = today();
  const todayAllowed = (!lo || lo <= now) && (!hi || hi >= startOfDay(now));
  const choose = (d: Date | undefined) => {
    onChange(d ? format(d, DAY) : "");
    setOpen(false);
  };
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <Trigger
        {...rest}
        icon={CalendarDays}
        text={picked ? format(picked, "d MMM yyyy") : ""}
        placeholder={placeholder}
        size={size}
        className={className}
        onClear={clearable ? () => onChange("") : undefined}
      />
      <PopoverContent align="start" className="w-auto p-2">
        <Calendar
          mode="single"
          selected={picked}
          onSelect={choose}
          defaultMonth={picked ?? (hi && hi < now ? hi : lo && lo > now ? lo : now)}
          disabled={disabled}
          startMonth={lo && lo < FIRST ? lo : FIRST}
          endMonth={hi && hi > LAST ? hi : LAST}
        />
        <Footer>
          <Button size="sm" variant="ghost" onClick={() => choose(undefined)} disabled={!picked}>
            Clear
          </Button>
          <Button size="sm" variant="ghost" onClick={() => choose(now)} disabled={!todayAllowed}>
            Today
          </Button>
        </Footer>
      </PopoverContent>
    </Popover>
  );
}

// --- a day and a time ------------------------------------------------------------------

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const MINUTES = Array.from({ length: 12 }, (_, i) => i * 5);
const two = (n: number) => String(n).padStart(2, "0");

function TimeColumn({
  label,
  items,
  value,
  onPick,
  show,
}: {
  label: string;
  items: number[];
  value: number | undefined;
  onPick: (n: number) => void;
  show: (n: number) => string;
}) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    box.current?.querySelector<HTMLElement>("[data-on=true]")?.scrollIntoView({ block: "center" });
  }, [value]);
  return (
    <div className="flex w-14 flex-col">
      <span className="pb-1 text-center text-[11px] font-medium text-muted-foreground">{label}</span>
      <div ref={box} role="listbox" aria-label={label} className="h-64 overflow-y-auto border-l [scrollbar-width:thin]">
        {items.map((n) => (
          <button
            key={n}
            type="button"
            role="option"
            aria-selected={n === value}
            data-on={n === value}
            onClick={() => onPick(n)}
            className={cn(
              "block w-full py-1 text-center text-sm tabular-nums hover:bg-accent",
              n === value && "bg-primary text-primary-foreground hover:bg-primary",
            )}
          >
            {show(n)}
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * Pick a day and a time. `value` / `onChange` are local "YYYY-MM-DDTHH:mm", the
 * same as `<input type="datetime-local">`; `min` is a day ("YYYY-MM-DD") or a stamp.
 */
export function DateTimePicker({
  value,
  onChange,
  min,
  max,
  placeholder = "Pick a date and time",
  size = "default",
  clearable = true,
  className,
  ...rest
}: Common & { value: string | undefined | null; onChange: (v: string) => void; min?: string; max?: string }) {
  const [open, setOpen] = useState(false);
  const picked = read(value, STAMP);
  const { lo, hi, disabled } = limits(min?.slice(0, 10), max?.slice(0, 10));
  const now = today();
  const set = (d: Date) => onChange(format(d, STAMP));
  const withDay = (day: Date | undefined) => {
    if (!day) return;
    const d = new Date(day);
    // A new pick keeps the time already chosen, or starts at the next whole hour.
    d.setHours(picked ? picked.getHours() : Math.min(23, now.getHours() + 1), picked ? picked.getMinutes() : 0);
    set(d);
  };
  const withTime = (h: number | null, m: number | null) => {
    const d = new Date(picked ?? now);
    d.setHours(h ?? d.getHours(), m ?? d.getMinutes(), 0, 0);
    set(d);
  };
  const minutes = picked && picked.getMinutes() % 5 ? [...MINUTES, picked.getMinutes()].sort((a, b) => a - b) : MINUTES;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <Trigger
        {...rest}
        icon={CalendarDays}
        text={picked ? format(picked, "d MMM yyyy, h:mm a") : ""}
        placeholder={placeholder}
        size={size}
        className={className}
        onClear={clearable ? () => onChange("") : undefined}
      />
      <PopoverContent align="start" className="w-auto p-2">
        <div className="flex">
          <Calendar
            mode="single"
            selected={picked}
            onSelect={withDay}
            defaultMonth={picked ?? (lo && lo > now ? lo : now)}
            disabled={disabled}
            startMonth={lo && lo < FIRST ? lo : FIRST}
            endMonth={hi && hi > LAST ? hi : LAST}
          />
          <div className="ml-1 flex">
            <TimeColumn
              label="Hour"
              items={HOURS}
              value={picked?.getHours()}
              onPick={(h) => withTime(h, null)}
              show={(h) => `${h % 12 || 12} ${h < 12 ? "am" : "pm"}`}
            />
            <TimeColumn
              label="Min"
              items={minutes}
              value={picked?.getMinutes()}
              onPick={(m) => withTime(null, m)}
              show={two}
            />
          </div>
        </div>
        <Footer>
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="size-3.5" />
            {picked ? format(picked, "EEE d MMM, h:mm a") : "Pick a day, then a time"}
          </span>
          <span className="flex gap-1">
            <Button size="sm" variant="ghost" onClick={() => set(now)}>
              Now
            </Button>
            <Button size="sm" onClick={() => setOpen(false)}>
              Done
            </Button>
          </span>
        </Footer>
      </PopoverContent>
    </Popover>
  );
}

// --- a range of days -------------------------------------------------------------------

type Range = { from: string; to: string };

/** The quick picks beside the range calendar. */
function presets(): { label: string; from: Date; to: Date }[] {
  const now = today();
  const lastMonth = subMonths(now, 1);
  return [
    { label: "Today", from: now, to: now },
    { label: "Yesterday", from: subDays(now, 1), to: subDays(now, 1) },
    { label: "Last 7 days", from: subDays(now, 6), to: now },
    { label: "Last 30 days", from: subDays(now, 29), to: now },
    { label: "This month", from: startOfMonth(now), to: now },
    { label: "Last month", from: startOfMonth(lastMonth), to: endOfMonth(lastMonth) },
    { label: "Last 90 days", from: subDays(now, 89), to: now },
    { label: "This year", from: startOfYear(now), to: now },
    {
      label: "Last year",
      from: startOfYear(subMonths(startOfYear(now), 1)),
      to: endOfYear(subMonths(startOfYear(now), 1)),
    },
  ];
}

function rangeText(from?: Date, to?: Date) {
  if (!from && !to) return "";
  if (from && !to) return `From ${format(from, "d MMM yyyy")}`;
  if (!from && to) return `Until ${format(to, "d MMM yyyy")}`;
  const a = from!;
  const b = to!;
  if (format(a, DAY) === format(b, DAY)) return format(a, "d MMM yyyy");
  if (a.getFullYear() === b.getFullYear()) return `${format(a, "d MMM")} – ${format(b, "d MMM yyyy")}`;
  return `${format(a, "d MMM yyyy")} – ${format(b, "d MMM yyyy")}`;
}

/**
 * Pick a span of days: two clicks on the calendar, or a quick pick. Either end may
 * be empty ("" = no limit). Strings are "YYYY-MM-DD".
 */
export function DateRangePicker({
  from,
  to,
  onChange,
  min,
  max,
  placeholder = "Any date",
  size = "default",
  clearable = true,
  showPresets = true,
  className,
  ...rest
}: Common & {
  from: string | undefined | null;
  to: string | undefined | null;
  onChange: (range: Range) => void;
  min?: string;
  max?: string;
  showPresets?: boolean;
}) {
  const [open, setOpen] = useState(false);
  // The first click of a new span; the second click finishes it.
  const [anchor, setAnchor] = useState<Date | null>(null);
  const a = read(from, DAY);
  const b = read(to, DAY);
  const { lo, hi, disabled } = limits(min, max);
  const now = today();
  const send = (x?: Date, y?: Date) => onChange({ from: x ? format(x, DAY) : "", to: y ? format(y, DAY) : "" });
  const click = (day: Date) => {
    if (!anchor) {
      setAnchor(day);
      send(day, day);
      return;
    }
    const [x, y] = day < anchor ? [day, anchor] : [anchor, day];
    setAnchor(null);
    send(x, y);
    setOpen(false);
  };
  const isPreset = (p: { from: Date; to: Date }) =>
    !!a && !!b && format(a, DAY) === format(p.from, DAY) && format(b, DAY) === format(p.to, DAY);
  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setAnchor(null);
      }}
    >
      <Trigger
        {...rest}
        icon={CalendarRange}
        text={rangeText(a, b)}
        placeholder={placeholder}
        size={size}
        className={cn(size === "sm" && "w-52", className)}
        onClear={clearable ? () => send() : undefined}
      />
      <PopoverContent align="start" className="w-auto max-w-[calc(100vw-1rem)] p-2">
        <div className="flex flex-col gap-2 sm:flex-row">
          {showPresets ? (
            <div className="flex flex-wrap gap-1 border-b pb-2 sm:w-32 sm:flex-col sm:flex-nowrap sm:border-r sm:border-b-0 sm:pr-2 sm:pb-0">
              {presets().map((p) => (
                <button
                  key={p.label}
                  type="button"
                  onClick={() => {
                    send(p.from, p.to);
                    setAnchor(null);
                    setOpen(false);
                  }}
                  className={cn(
                    "px-2 py-1 text-left text-xs hover:bg-accent sm:text-sm",
                    isPreset(p) && "bg-primary/10 font-medium text-primary",
                  )}
                >
                  {p.label}
                </button>
              ))}
            </div>
          ) : null}
          <Calendar
            mode="range"
            selected={a || b ? { from: a, to: b } : undefined}
            onDayClick={(day, m) => (m.disabled ? undefined : click(day))}
            numberOfMonths={2}
            defaultMonth={a ? a : subMonths(b ?? now, 1)}
            disabled={disabled}
            startMonth={lo && lo < FIRST ? lo : FIRST}
            endMonth={hi && hi > LAST ? hi : LAST}
          />
        </div>
        <Footer>
          <span className="text-xs text-muted-foreground">
            {anchor ? "Now pick the last day" : rangeText(a, b) || "Pick the first day"}
          </span>
          <span className="flex gap-1">
            <Button size="sm" variant="ghost" onClick={() => send()} disabled={!a && !b}>
              Clear
            </Button>
            <Button size="sm" onClick={() => setOpen(false)}>
              Done
            </Button>
          </span>
        </Footer>
      </PopoverContent>
    </Popover>
  );
}

// --- a month ---------------------------------------------------------------------------

/** Pick a month. `value` / `onChange` are "YYYY-MM", like `<input type="month">`. */
export function MonthPicker({
  value,
  onChange,
  min,
  max,
  placeholder = "Pick a month",
  size = "default",
  clearable = false,
  className,
  ...rest
}: Common & { value: string | undefined | null; onChange: (v: string) => void; min?: string; max?: string }) {
  const [open, setOpen] = useState(false);
  const picked = read(value, MONTH);
  const [year, setYear] = useState(() => (picked ?? today()).getFullYear());
  const lo = read(min, MONTH);
  const hi = read(max, MONTH);
  const off = (m: number) => {
    const d = new Date(year, m, 1);
    return (!!lo && d < lo) || (!!hi && d > hi);
  };
  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (o) setYear((picked ?? today()).getFullYear());
      }}
    >
      <Trigger
        {...rest}
        icon={CalendarDays}
        text={picked ? format(picked, "MMMM yyyy") : ""}
        placeholder={placeholder}
        size={size}
        className={className}
        onClear={clearable ? () => onChange("") : undefined}
      />
      <PopoverContent align="start" className="w-64 p-2">
        <div className="flex items-center justify-between">
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label="Previous year"
            onClick={() => setYear(year - 1)}
            disabled={!!lo && year <= lo.getFullYear()}
          >
            <ChevronLeft />
          </Button>
          <span className="text-sm font-medium tabular-nums">{year}</span>
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label="Next year"
            onClick={() => setYear(year + 1)}
            disabled={!!hi && year >= hi.getFullYear()}
          >
            <ChevronRight />
          </Button>
        </div>
        <div className="grid grid-cols-3 gap-1">
          {Array.from({ length: 12 }, (_, m) => {
            const on = !!picked && picked.getFullYear() === year && picked.getMonth() === m;
            const now = today();
            const current = now.getFullYear() === year && now.getMonth() === m;
            return (
              <button
                key={m}
                type="button"
                disabled={off(m)}
                onClick={() => {
                  onChange(format(new Date(year, m, 1), MONTH));
                  setOpen(false);
                }}
                className={cn(
                  "py-2 text-sm hover:bg-accent disabled:pointer-events-none disabled:opacity-40",
                  current && "font-semibold ring-1 ring-primary/60 ring-inset",
                  on && "bg-primary text-primary-foreground hover:bg-primary",
                )}
              >
                {format(new Date(year, m, 1), "MMM")}
              </button>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}
