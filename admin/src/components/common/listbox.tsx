"use client";

import { Check, ChevronDown } from "lucide-react";
import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/utils";

/*
 * The panel's dropdown, written without a UI library so nothing of it is left on
 * the page once it closes: the list is mounted while open and removed the moment
 * it shuts — no exit animation that can hang and leave a see-through list over
 * the table. It opens below the box (above when there's no room), follows the box
 * on scroll, and works from the keyboard (arrows, Home/End, Enter, Esc, typing).
 */

export type ListboxOption = { value: string; label: ReactNode; text?: string; disabled?: boolean };

type Props = {
  /** `{ value: label }`, or a list of options. */
  items: Record<string, ReactNode> | ListboxOption[];
  value: string | null | undefined;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  id?: string;
  className?: string;
  /** The list's own width, when the box is narrow. Defaults to the box's width. */
  listClassName?: string;
  "aria-label"?: string;
  "aria-invalid"?: boolean;
};

type Place = { top?: number; bottom?: number; left: number; minWidth: number; maxHeight: number };

const plain = (n: ReactNode) => (typeof n === "string" || typeof n === "number" ? String(n) : "");

export function Listbox({
  items,
  value,
  onChange,
  placeholder = "Choose…",
  disabled,
  id,
  className,
  listClassName,
  ...aria
}: Props) {
  const options: ListboxOption[] = Array.isArray(items)
    ? items
    : Object.entries(items).map(([v, label]) => ({ value: v, label }));
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [place, setPlace] = useState<Place | null>(null);
  const [host, setHost] = useState<HTMLElement | null>(null);
  const box = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const typed = useRef({ text: "", at: 0 });
  const listId = useId();
  const chosen = options.findIndex((o) => o.value === value);

  const measure = useCallback(() => {
    const el = box.current;
    if (!el) return;
    // Inside a dialog or sheet the list goes into it (so a click on the list isn't
    // a click "outside" the dialog). Many CSS properties there change what
    // `position: fixed` is measured from, so ask the browser rather than guess.
    const container = el.closest<HTMLElement>("[role=dialog],[role=alertdialog]") ?? document.body;
    const probe = document.createElement("div");
    probe.style.cssText = "position:fixed;inset:0;visibility:hidden;pointer-events:none";
    container.appendChild(probe);
    const origin = probe.getBoundingClientRect();
    probe.remove();
    const r = el.getBoundingClientRect();
    const below = window.innerHeight - r.bottom - 8;
    const above = r.top - 8;
    const wanted = Math.min(320, options.length * 32 + 8);
    const down = below >= wanted || below >= above;
    const left = Math.max(8, Math.min(r.left, window.innerWidth - Math.max(r.width, 144) - 8));
    setHost(container);
    setPlace({
      ...(down ? { top: r.bottom + 4 - origin.top } : { bottom: origin.bottom - r.top + 4 }),
      left: left - origin.left,
      minWidth: Math.max(r.width, 144),
      maxHeight: Math.max(120, Math.min(320, (down ? below : above) - 4)),
    });
  }, [options.length]);

  const close = useCallback((refocus = true) => {
    setOpen(false);
    setPlace(null);
    if (refocus) box.current?.focus();
  }, []);

  const show = () => {
    if (disabled) return;
    measure();
    setActive(chosen >= 0 ? chosen : options.findIndex((o) => !o.disabled));
    setOpen(true);
  };

  const pick = (i: number) => {
    const o = options[i];
    if (!o || o.disabled) return;
    if (o.value !== value) onChange(o.value);
    close();
  };

  // While open: follow the box, and close on a press anywhere else.
  useLayoutEffect(() => {
    if (!open) return;
    const follow = () => measure();
    const outside = (e: PointerEvent) => {
      const t = e.target as Node;
      if (!box.current?.contains(t) && !list.current?.contains(t)) close(false);
    };
    window.addEventListener("scroll", follow, true);
    window.addEventListener("resize", follow);
    document.addEventListener("pointerdown", outside, true);
    return () => {
      window.removeEventListener("scroll", follow, true);
      window.removeEventListener("resize", follow);
      document.removeEventListener("pointerdown", outside, true);
    };
  }, [open, measure, close]);

  // Keep the highlighted option in view.
  useEffect(() => {
    if (!open || active < 0) return;
    list.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  const step = (from: number, by: 1 | -1) => {
    for (let i = from + by, n = 0; n < options.length; i += by, n++) {
      const at = (i + options.length) % options.length;
      if (!options[at].disabled) return at;
    }
    return from;
  };

  const onKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;
    const k = e.key;
    if (!open) {
      if (k === "ArrowDown" || k === "ArrowUp" || k === "Enter" || k === " ") {
        e.preventDefault();
        show();
      }
      return;
    }
    if (k === "Escape" || k === "Tab") {
      if (k === "Escape") e.preventDefault();
      close(k === "Escape");
    } else if (k === "ArrowDown") {
      e.preventDefault();
      setActive((a) => step(a, 1));
    } else if (k === "ArrowUp") {
      e.preventDefault();
      setActive((a) => step(a < 0 ? options.length : a, -1));
    } else if (k === "Home") {
      e.preventDefault();
      setActive(step(-1, 1));
    } else if (k === "End") {
      e.preventDefault();
      setActive(step(options.length, -1));
    } else if (k === "Enter" || k === " ") {
      e.preventDefault();
      pick(active);
    } else if (k.length === 1 && /\S/.test(k)) {
      // Type the start of an option to jump to it.
      const now = Date.now();
      typed.current = { text: (now - typed.current.at < 700 ? typed.current.text : "") + k.toLowerCase(), at: now };
      const hit = options.findIndex(
        (o) => !o.disabled && (o.text ?? plain(o.label)).toLowerCase().startsWith(typed.current.text),
      );
      if (hit >= 0) setActive(hit);
    }
  };

  const label = chosen >= 0 ? options[chosen].label : null;

  return (
    <>
      <button
        ref={box}
        id={id}
        type="button"
        role="combobox"
        data-slot="listbox-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined}
        disabled={disabled}
        onClick={() => (open ? close() : show())}
        onKeyDown={onKey}
        {...aria}
        className={cn(
          "flex h-9 w-full min-w-0 items-center gap-2 rounded-none border border-input bg-transparent pr-2 pl-2.5 text-left text-sm transition-colors outline-none dark:bg-input/30",
          "hover:border-ring/60 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
          "disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive",
          open && "border-ring",
          className,
        )}
      >
        <span className={cn("min-w-0 flex-1 truncate", label === null && "text-muted-foreground")}>
          {label ?? placeholder}
        </span>
        <ChevronDown
          className={cn(
            "size-4 shrink-0 text-muted-foreground transition-transform duration-150",
            open && "rotate-180",
          )}
        />
      </button>
      {open && place && host
        ? createPortal(
            <div
              ref={list}
              id={listId}
              role="listbox"
              tabIndex={-1}
              // Keep focus on the box: the list is driven from it.
              onMouseDown={(e) => e.preventDefault()}
              style={{
                position: "fixed",
                top: place.top,
                bottom: place.bottom,
                left: place.left,
                minWidth: place.minWidth,
                maxHeight: place.maxHeight,
              }}
              className={cn(
                "z-[60] max-w-[min(24rem,calc(100vw-1rem))] animate-in overflow-y-auto overscroll-contain border bg-popover py-1 text-sm text-popover-foreground shadow-lg ring-1 ring-foreground/5 duration-100 fade-in-0 [scrollbar-width:thin]",
                place.top !== undefined ? "slide-in-from-top-1" : "slide-in-from-bottom-1",
                listClassName,
              )}
            >
              {options.length ? (
                options.map((o, i) => (
                  <div
                    key={o.value}
                    id={`${listId}-${i}`}
                    data-index={i}
                    role="option"
                    aria-selected={i === chosen}
                    aria-disabled={o.disabled || undefined}
                    onPointerMove={() => !o.disabled && active !== i && setActive(i)}
                    onClick={() => pick(i)}
                    className={cn(
                      "flex cursor-default items-center gap-2 px-2.5 py-1.5 select-none",
                      i === active && "bg-accent text-accent-foreground",
                      i === chosen && "font-medium",
                      o.disabled && "opacity-50",
                    )}
                  >
                    <span className="min-w-0 flex-1 truncate">{o.label}</span>
                    {i === chosen ? <Check className="size-4 shrink-0 text-primary" /> : null}
                  </div>
                ))
              ) : (
                <p className="px-2.5 py-1.5 text-muted-foreground">Nothing to choose</p>
              )}
            </div>,
            host,
          )
        : null}
    </>
  );
}
