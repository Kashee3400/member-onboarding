"use client";

import { useBranding } from "@/hooks/use-session";

import { Kbd } from "./shortcuts-help";

/** A quiet line under each page, which also teaches the one shortcut worth learning. */
export function PanelFooter() {
  const branding = useBranding();
  return (
    <footer className="z-10 flex h-10 shrink-0 items-center justify-between gap-3 border-t bg-background/90 px-4 text-xs text-muted-foreground backdrop-blur md:sticky md:bottom-0 md:px-6">
      <span>
        © {new Date().getFullYear()} {branding.display_name}
      </span>
      <span className="hidden items-center gap-1.5 sm:flex">
        Keyboard shortcuts <Kbd>?</Kbd>
      </span>
    </footer>
  );
}
