"use client";

import { Keyboard } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { isTyping } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";

/** A key, drawn like one. */
export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center border bg-muted px-1 font-mono text-[10px] font-medium text-muted-foreground",
        className,
      )}
    >
      {children}
    </kbd>
  );
}

const SECTIONS: { title: string; keys: [string[], string][] }[] = [
  {
    title: "Anywhere",
    keys: [
      [["Ctrl", "K"], "Search forms, members and pages"],
      [["Alt", "S"], "Go to the menu"],
      [["Ctrl", "B"], "Fold the menu to icons"],
      [["/"], "Jump to this page's search box"],
      [["?"], "Show these shortcuts"],
    ],
  },
  {
    title: "In the menu",
    keys: [
      [["↑", "↓"], "Move up and down"],
      [["Enter"], "Open the page, or fold and unfold a group"],
      [["→"], "Open a group"],
      [["←"], "Close a group, or go back to its heading"],
      [["A-Z"], "Jump to the next row starting with that letter"],
      [["Esc"], "Back to the page"],
    ],
  },
  {
    title: "Approval queues",
    keys: [
      [["J"], "Next item"],
      [["K"], "Previous item"],
      [["A"], "Approve the form, after asking"],
      [["D"], "Open the form with the reject dialog"],
      [["Enter"], "Open it"],
      [["Esc"], "Stop"],
    ],
  },
  {
    title: "On a form",
    keys: [
      [["A"], "Approve the step on screen, after asking"],
      [["R"], "Reject, with a reason"],
      [["J"], "Previous form in the queue"],
      [["K"], "Next form in the queue"],
      [["1-8"], "Open that step's tab"],
    ],
  },
];

/** "?" anywhere opens the list of keyboard shortcuts. */
export function ShortcutsHelp() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "?" && !isTyping(e)) {
        e.preventDefault();
        setOpen(true);
      }
    };
    const show = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("mo:shortcuts", show);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mo:shortcuts", show);
    };
  }, []);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {/* Capped to the screen: the heading stays put and only the list scrolls. */}
      <DialogContent className="flex max-h-[85svh] flex-col sm:max-w-lg">
        <DialogHeader className="shrink-0">
          <DialogTitle className="flex items-center gap-2">
            <Keyboard className="size-4" /> Keyboard shortcuts
          </DialogTitle>
          <DialogDescription>They do nothing while you are typing in a box.</DialogDescription>
        </DialogHeader>
        <div className="-mr-2 min-h-0 flex-1 space-y-5 overflow-y-auto overscroll-contain pr-2" tabIndex={0}>
          {SECTIONS.map((s) => (
            <section key={s.title} className="space-y-2">
              <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">{s.title}</h3>
              <ul className="space-y-1.5 text-sm">
                {s.keys.map(([keys, what]) => (
                  <li key={what} className="flex items-center justify-between gap-4">
                    <span>{what}</span>
                    <span className="flex shrink-0 gap-1">
                      {keys.map((k) => (
                        <Kbd key={k}>{k}</Kbd>
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
