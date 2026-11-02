"use client";

import { useEffect, useRef, useState } from "react";

/** The key press happened while typing in a box — shortcuts must leave it alone. */
export function isTyping(e: KeyboardEvent): boolean {
  const el = e.target as HTMLElement | null;
  if (!el) return false;
  if (el.isContentEditable) return true;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || !!el.closest("[role=dialog],[role=alertdialog]");
}

export type ListKeys = {
  /** A — the "yes" action on the focused item (approve, confirm, mark ready). */
  onApprove?: (index: number) => void;
  /** D — the "no" action (dismiss, reject, hide). */
  onDismiss?: (index: number) => void;
  /** Enter / O — open it. */
  onOpen?: (index: number) => void;
};

/**
 * J / K move through a review queue, A / D act on the focused item, Enter opens
 * it. Without handlers, A / D / Enter press the focused item's button marked
 * `data-shortcut="approve"` / `"dismiss"` / `"open"` — so a page only marks its
 * buttons. Returns the focused index, a ref setter per item and the outline class.
 */
export function useListKeys(count: number, keys: ListKeys = {}) {
  const [focused, setFocused] = useState(-1);
  const refs = useRef<(HTMLElement | null)[]>([]);
  const latest = useRef(keys);
  useEffect(() => {
    latest.current = keys;
  });

  // Keep the focus inside the list when it shrinks (an item was acted on).
  const at = focused >= count ? count - 1 : focused;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTyping(e) || e.metaKey || e.ctrlKey || e.altKey) return;
      const key = e.key.toLowerCase();
      if (key === "j" || key === "k") {
        e.preventDefault();
        setFocused((f) => {
          const from = f >= count ? count - 1 : f;
          const next = key === "j" ? Math.min(count - 1, from + 1) : Math.max(0, from - 1);
          refs.current[next]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
          return next;
        });
        return;
      }
      if (at < 0 || at >= count) return;
      const press = (name: string) => {
        const button = refs.current[at]?.querySelector<HTMLElement>(`[data-shortcut="${name}"]:not([disabled])`);
        if (!button) return false;
        e.preventDefault();
        button.click();
        return true;
      };
      if (key === "a") {
        if (latest.current.onApprove) {
          e.preventDefault();
          latest.current.onApprove(at);
        } else press("approve");
      } else if (key === "d") {
        if (latest.current.onDismiss) {
          e.preventDefault();
          latest.current.onDismiss(at);
        } else press("dismiss");
      } else if (key === "enter" || key === "o") {
        if (latest.current.onOpen) {
          e.preventDefault();
          latest.current.onOpen(at);
        } else press("open");
      } else if (key === "escape") {
        setFocused(-1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [count, at]);

  return {
    focused: at,
    itemRef: (i: number) => (el: HTMLElement | null) => {
      refs.current[i] = el;
    },
    /** The ring that shows which item J / K reached. */
    focusClass: (i: number) => (i === at ? "ring-2 ring-primary ring-offset-2 ring-offset-background" : ""),
    setFocused,
  };
}
